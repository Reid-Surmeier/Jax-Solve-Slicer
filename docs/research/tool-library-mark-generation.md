# Tool-library mark generation

Research for the owner's question about turning each alpha plate into marks made only by a small library of physical dipping tools. Dated **2026-09-23**. It builds on [Painting toolpath options](painting-toolpath-options.md) and does not repeat it. It feeds the map in [issue 1](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/1) and the open output question in [issue 4](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/4).

This is a research report. It changes no code, module interface or git state.

## Executive finding

**Treat the alpha-to-SVG step as a style pass driven by rules, not as an optimizer.** The alpha plate says *where* ink goes and *how much*. A small recipe for each plate says *how*: which of the ~5 tools to use, dab or drag, which direction, grid cells or free placement, and how many marks per cell. This is how stroke-based rendering has worked since Haeberli and Hertzmann. Hertzmann's own survey says the rules are the artist's contribution ([SBR course notes, SIGGRAPH 2002](https://www.dgp.toronto.edu/~hertzman/sbr02/hertzmann-sbr02.pdf), §1).

**Build it in plain Python and NumPy as a drop-in replacement for `alpha_masks_to_coverage_paths`. Do not use Blender or JAX for this step.** Blender is out by the owner's decision. JAX adds nothing to rule-based placement, and it is not installed in this checkout. The new stage reads a `tools.json` library and one recipe per plate, places fixed tool footprints (never scaled), and writes SVG in which every mark has `data-tool`, `data-mode`, `data-dip` and `data-seq`. It also reports a loose legibility check comparing the SVG with the plate. The current converter never measures this.

**Geometry Nodes question:** the Blender graph does run and exports real evaluated geometry. It is a random-density sampler, though, not a tool-selection system. It places points on a grid, keeps each one with probability `alpha × density`, and stamps **one globally chosen** footprint, **scaled** by global length and width, at a per-plate angle plus random jitter. There is no per-mark tool choice, no fit to the target, no ink or dip model, and no mark order. Details are under [Is Geometry Nodes really working?](#is-geometry-nodes-really-working).

The first experiment is two recipes: a Chuck Close-style grid of cells, and long directional drags. Run them on the existing 12-plate reproduction with a hand-written 5-tool library. See [First experiment](#first-experiment-drop-in-replacement).

## What the repository actually does today (verified)

### The alpha solve is JAX; everything around it is NumPy

- `solve_alpha_stack_jax` in [`generate_micron_alpha_plates.py`](../../modules/legacy/scripts/generate_micron_alpha_plates.py) (lines 256–344) is real JAX. It keeps sigmoid logits for each pixel and each plate, runs a hand-written Adam loop inside `jax.lax.fori_loop` under `jax.jit`, works in tiles of 65,536 pixels, and minimises RGB MSE + 0.35·luminance MSE + a small prior toward the seed. Plates are composited in order as `out·(1−a) + ink·a` over paper.
- The seed (`initialize_alpha_stack`, [`plate_solver.py`](../../modules/legacy/src/plotter_separation/plate_solver.py)) and the final composite and metrics ([`overprint.py`](../../modules/legacy/src/plotter_separation/overprint.py)) are NumPy.
- Pixels are solved independently. The loss has no spatial term, so an alpha plate is a per-pixel coverage map with no idea of marks, tools or neighbourhoods. Any mark structure has to come from the SVG stage.
- The reproduction metadata records `backend: jax_soft_alpha_direct`, 700 steps, 12 inks, and a 369 × 459 px working size. The report says JAX 0.10.0 ran on CUDA ([reproduction README](../reproduction/2026-09-20/README.md)).
- **JAX is not importable** from either the system `python3` or the repo `.venv` (checked 2026-09-23: `ModuleNotFoundError`), and `requirements-prototype.txt` pins only NumPy, Pillow and pymixbox. The saved `alpha_stack_float32.npz` (12 × 459 × 369, float32) is enough input for the new stage. JAX is needed only to solve again from a source image.

### The alpha→SVG converter in use

This is `alpha_masks_to_coverage_paths` + `_coverage_cell_paths` in [`markmaking.py`](../../modules/legacy/src/plotter_line_drawing_svg/markmaking.py):

1. Split each plate into square tiles (`auto_tile_px` gives 5 px for this image) and average the alpha in each tile. Skip tiles below `min_alpha = 0.025`.
2. Set `coverage = clip(local / 0.55, 0.035, 0.96)` and make `ceil(coverage × 3)` marks (1 to 3).
3. Draw each mark as a jittered rectangle. Its **area** is `coverage × cell area / count`, so its **width is computed** (`band_width = mark_area / length`). Its angle is one of six base angles for the plate, plus a hash-based jitter.
4. Keep the top 7,200 marks per plate, ranked by `local × area`. Every mark is drawn with `fill-opacity 0.55`.

In short, it runs open-loop, uses one mark shape whose size varies, has no tool identity, no order and no dips. It does rasterise the SVG (`rasterize_svg_artwork` → `actual_svg_crop.png`), but only for the contact sheet. No numeric comparison of the SVG against the plate or target is computed anywhere (grep for `rmse`/`error` in `plotter_line_drawing_svg/`). The RMSE of 0.0171 reported for the latest run is the alpha composite, not the SVG.

Its tile loop is already the skeleton of a Close-style grid. The new stage keeps the loop and replaces steps 2–4.

## Is Geometry Nodes really working?

Read from [`modules/blender_recipes/prototype.py`](../../modules/blender_recipes/prototype.py), `make_group` (lines 35–144) and `main`:

| Step in the graph | What it actually does |
| --- | --- |
| `Mesh Grid` | A regular point grid over the canvas. The vertex count is `canvas / spacing`, so the real pitch is only close to `spacing`. |
| `Image Texture` on position | Samples the plate's value at each point (nearest pixel lookup through a normalised position). |
| `Random Value` > `alpha × Density` → `Delete Geometry` | Keeps each point with probability `min(1, alpha × density)`. This is random dithering, with no check of the density it produces. |
| Two `Switch` nodes on `Recipe 0 hatch 1 curve 2 stamp` | Picks **one** of three hard-coded meshes. The control is driven from a single `RECIPE CONTROLS` object, so **every plate and every mark uses the same tool**. |
| `Instance on Points` | Stamps that mesh with rotation = the plate's `Rotation degrees` (0/90/45/−45/22.5/−22.5) + `(random − 0.5) × jitter`, and scale = `(Length mm, Width mm, 1)`. **The footprint is scaled, not fixed.** |
| `Realize Instances` → `export_svg` | Writes each evaluated polygon as a filled path with `fill-opacity 0.55`. It has no mark id, no tool id, no order and no dip. A diamond impression becomes four polygons. |

**What it does:** it evaluates real node geometry in Blender, stays editable in the `.blend`, and exports millimetre SVG that matches the scene. Its only automated check proves that a larger spacing gives fewer polygons (lines 244–249).

**What it does not do:** it cannot choose a tool for each mark or region, and it does not fit or measure anything against the alpha target. It has no ink, dip or depletion model, no dab-versus-drag distinction, no mark sequence, and no fixed physical footprint.

**Inferred, not tested:** the rotation jitter comes from a `Random Value` node with no ID input, and grid meshes carry no `id` attribute. The value is therefore probably keyed to point index after deletion. If so, changing density reshuffles the jitter of unrelated marks, which hurts the stability the owner wants from editing.

It works as a demo of Blender instancing. It does not solve the tool-library problem, which is consistent with the owner's decision to take Blender out of this step.

## Prior art that fits a rule-based style pass

### Stroke-based rendering: rules first, error-checking second

- Hertzmann (1998) paints layer by layer, from large brushes to small. On a grid whose spacing is set by brush size, it adds a stroke only where the mean canvas-versus-reference error in the cell is above a threshold T. Strokes follow the normal of the image gradient and have minimum and maximum lengths. "All strokes for the layer are planned at once before rendering," and are then drawn in random order ([Painterly Rendering with Curved Brush Strokes of Multiple Sizes, SIGGRAPH 98](https://mrl.cs.nyu.edu/publications/painterly98/hertzmann-siggraph98.pdf), §2.1–2.2). This is a style recipe with a cheap gate, not an optimizer. Its parameters (thresholds, brush sizes, grid factor, stroke length) are the controls the owner is asking for.
- Hertzmann's survey divides SBR into **greedy** placement and **optimization**. It says a user "should be able to specify spatially-varying styles, so that different rendering styles are used in different parts of the image" ([SBR course notes](https://www.dgp.toronto.edu/~hertzman/sbr02/hertzmann-sbr02.pdf), §1). These are the SIGGRAPH 2002 course notes. The 2003 IEEE CG&A survey is the published version, which was not fetched here.
- **Prioritized stroke textures** (Salisbury et al., SIGGRAPH 94, as described in the survey §4 / Fig. 11) draw strokes in a fixed priority order, so one texture can produce many tones. More coverage means drawing further down the list. This is the right model for "1 to 3 marks per cell": each plate recipe has an ordered mark list, and cell alpha decides how far down it goes.
- Weighted Voronoi stippling places identical dots by density-weighted Lloyd relaxation ([Secord, NPAR 2002](https://www.cs.ubc.ca/labs/imager/tr/2002/secord2002b/secord.2002b.pdf)). The paper uses constant stipple radii and names varying stipple size and colour as **future work**. It supports placing fixed primitives by density, and it is a possible later "free placement" layout. It is not needed for the first experiment.

### Chuck Close's grid

- The Walker Art Center: "In the mid-1980s, he began to emphasize the grid itself by using larger, looser marks that turned each square into a self-contained, miniature abstraction" ([Walker, Chuck Close](https://www.walkerart.org/collections/artist/chuck-close/)).
- Met exhibition text (*Chuck Close Prints: Process and Collaboration*): the heads are "conceived as a series of gridded abstractions that, when assembled in the eye of the viewer, coalesce into a representational whole", and *Emma* (2002) is "a gridded abstraction of brilliantly colored loops, dots, and lozenges" ([Met press release](https://www.metmuseum.org/press-releases/chuck-close-prints--process-and-collaboration-2003-exhibitions); the Met page blocked automated fetches, so the text was read from the [Met-supplied reprint at TFAOI](https://www.tfaoi.org/aa/4aa/4aa207.htm)).
- Whitney, *Phil* (1969): a pencilled grid on the photo, with each square enlarged onto the canvas ([Whitney](https://whitney.org/collection/works/1425)).
- Close himself: "there's a difference between going directly to a color … and slowly finding a color by putting several together and building them until you get exactly what you want", and "over the years, the dot grid got coarser … there was more room inside the square" ([BOMB, 1995](https://bombmagazine.org/articles/1995/07/01/chuck-close/)).
- **Not verified:** no museum record was found for a 1986 watercolour titled *Judy*. The grid-cell model below rests on the sources above, not on that work.

For this project this means one grid cell per plate, 1–3 layered marks from a small vocabulary (dab, ring, diamond, lozenge), and a colour/tone that averages out at viewing distance. Layering across plates is already handled by the alpha stack. Each plate needs only its own mark vocabulary per cell.

### Robotic painting with physical tools and dips

- **e-David** (Deussen et al., [CAe 2012](https://geometry.stanford.edu/lgl_2024/papers/dlpt-fgsppm-12/dlpt-fgsppm-12.pdf), §3–4): it holds five brushes, and dips "by mechanically opening the cover plate and dipping the brush into the color". The paper notes that for some paints "only short strokes can be realized after dipping", and that these characteristics "are stored by the robot server in brush and paint color profiles". Its simplest planner uses a **predefined set of stroke candidates** (180 fixed-size paths at different orientations), scores each one against the target, and keeps the best. This is the closest published match to a fixed tool library with a stored limit on marks per dip.
- **FRIDA** (Schaldenbrand, McCann, Oh, [arXiv 2210.00664](https://arxiv.org/abs/2210.00664); [repo, GPL-3.0](https://github.com/cmubig/Frida), read at `f42fa61`) learns a `param2stroke` network. It maps (length, bend, thickness) to a stroke appearance map, trained on photographs of random real robot strokes, and the paper reports small gains beyond about 100 strokes (Appendix B). Strokes are composited over the canvas in order (`src/painting.py`). The paper lists these limitations: "brush strokes assumed to be independent, no modelling of the wetness of paint, not modeling how much paint is on the brush" (§VI), and calls paint load "the most significant unaccounted for variable" (Appendix B). In code, dipping follows a **fixed cadence** (`--how_often_to_get_paint`, default 4, `src/options.py`; used in `src/paint.py`).

**What to take from them:** scan real tool impressions and use them as footprints, store the dip limit in a per-tool profile, and use a fixed dip cadence. Even the most elaborate system here does not model depletion. The rest of FRIDA (CLIP/style losses, gradient replanning) serves fidelity and semantics, which is not the goal here.

## Tool model: fixed, scanned, with dip limits

A tool is data, not code. Minimal `tools.json` entry:

| Field | Meaning | Source |
| --- | --- | --- |
| `id` | Stable name, e.g. `sponge-12` | owner |
| `footprint` | Grayscale PNG of one fresh impression; darkness = ink density | scan |
| `px_per_mm` | Scan resolution, so the footprint has true size | scan |
| `mode` | `dab` (stamp once) or `drag` (footprint swept along a centerline) | owner |
| `rotations` | Allowed angles in degrees, or `any`; a round sponge can be `[0]` | owner |
| `per_dip` | Impressions per dip (`dab`) or mm of drag per dip (`drag`) | test sheet |
| `density` | Mean ink density of a fresh impression (0–1), replacing the global 0.55 | scan |

**Calibration sheet (one per tool, no code):** dip once, then stamp repeatedly (or drag one long stroke) until the tool runs dry, and scan at known dpi. The first impression becomes `footprint`. Its mean darkness becomes `density`. The number of impressions (or mm) that still read as intended becomes `per_dip`. This is FRIDA's scan-real-strokes idea cut down to a fixed tool.

**Deliberately left out for now (premature):**

- **Depletion fade.** Successive impressions get lighter, and FRIDA does not model this either. Keep the scans, and add a per-impression fade curve only if the preview visibly misleads.
- **Drag deposition along length.** Preview a drag as the footprint swept along the centerline at constant density. Tapering is a later refinement from the same scans.
- **Mixbox or wet mixing between plates.** Keep the RGB baseline. Mixbox stays a comparison renderer, as in the prior note.
- **Pressure and scale.** The footprint is never scaled. A different size is a different tool.

## Recipes: how a plate becomes marks

A recipe is a few declared rules per plate. Regions are left out of the first experiment (see the prior note for guides and regions).

**Recipe G: Close-style grid cells**

```text
layout: grid, cell_mm: 6, lattice: square | diamond(45°)
marks: [sponge-6 dab, ring-8 dab, sponge-3 dab]   # priority order
levels: [0.12, 0.35, 0.6]                          # alpha thresholds for 1st, 2nd, 3rd mark
placement: centre, then fixed offsets inside cell; rotation from tool.rotations
```

For each cell, compute the mean alpha and draw as many marks from the priority list as it passes thresholds. Offsets are deterministic per cell, so an edit changes only that cell.

Default thresholds can come from a lookup table instead of hand-tuning. Rasterise each prefix of the mark list once into a cell-sized image, measure its coverage (mean footprint density), and use the midpoints between successive prefixes as thresholds. This is one table per plate, computed once, not an optimizer.

**Recipe D: long directional drags**

```text
layout: lines at angle 35°, spacing = tool width
tool: flat-20 drag, on: 0.30, off: 0.18, min_mm: 15, max_mm: per_dip
```

Walk each line across the plate and sample alpha along it. Start a drag when alpha rises above `on`, and end it when alpha falls below `off` (hysteresis stops chatter) or when the drag reaches `per_dip`. Drop drags shorter than `min_mm`. Emit the centerline, not a filled outline.

**Recipe S (optional third): scattered dabs** ("leaf-like dabs in red"). Distribute a mark budget across cells by mass. `_systematic_weighted_counts` already exists in `markmaking.py`. Place each dab at a hashed position inside its cell, rotated by the plate angle ± jitter within `tool.rotations`.

The reference style maps onto these directly: yellow → D with the flat tool, blue and black → D with a narrow tool and a small `spacing`, red → S with a leaf-shaped stamp. Close style is G on every plate.

## Output contract

SVG stays the single deliverable, in millimetres, one `<g>` per plate in ink order:

```xml
<metadata>{"tools_sha256": "…", "recipe": {…}, "alpha_sha256": "…"}</metadata>
<defs><symbol id="tool-ring-8">…footprint outline…</symbol></defs>
<g id="plate-04-yellow" data-ink="xsdk05_003">
  <path d="M… L…" data-tool="flat-20" data-mode="drag" data-dip="3" data-seq="41"
        fill="none" stroke="#f5c41c" stroke-width="20" stroke-opacity="0.8"/>
  <use href="#tool-ring-8" x="…" y="…" transform="rotate(…)" data-tool="ring-8"
       data-mode="dab" data-dip="7" data-seq="42"/>
</g>
```

- `data-seq` is the execution order inside a plate: group by tool, then serpentine rows (boustrophedon) for travel. A new `data-dip` starts every `per_dip` impressions or mm, and whenever the tool changes. Better travel ordering (vpype `linesort`) is a later post-process, as covered in the prior note.
- The preview uses stroke width and opacity from `tools.json`. It is a visual stand-in, not a physical prediction, and the SVG should say so in `<metadata>`.
- Motion format, contact height and G-code are out of scope until the machine contract exists.

## Why not optimization now, and when

- **The goal is style, not fidelity.** Optimization would move marks toward the source image, which removes exactly the gesture the recipes add.
- **Discrete tool choice is not differentiable.** The usual workarounds are a Gumbel-softmax relaxation ([Jang, Gu, Poole 2016](https://arxiv.org/abs/1611.01144)), or continuous parameters that are periodically snapped to the discrete set. FRIDA does the latter for paint colours: k-means, then `discretize_colors` every 10 iterations late in optimization (`src/painting_optimization.py`). Both add machinery that five tools do not need. Enumerating 5 tools × a handful of rotations per slot is exact and cheap.
- **Pixel losses give fixed stamps weak position gradients.** Stylized Neural Painting shows that an L1/L2 pixel loss has zero gradient when a stroke does not overlap its target, and switches to an optimal-transport loss for that reason ([Zou et al. 2020](https://arxiv.org/abs/2011.08114), §3). DiffVG makes vector rasterisation differentiable through prefiltering ([Li et al., SIGGRAPH Asia 2020](https://people.csail.mit.edu/tzumao/diffvg/)), but it does not handle discrete choices. Learning to Paint ([Huang et al. 2019](https://arxiv.org/abs/1903.04411)) and Paint Transformer ([Liu et al. 2021](https://arxiv.org/abs/2108.03798)) train networks for continuous stroke parameters. Neither has a fixed tool library, and FRIDA reports that Learning to Paint's strokes transfer poorly to a real robot (FRIDA §V, Fig. 9).
- **When to revisit:** only if a recipe's output stops reading as the image. The next step then is a greedy local gate, not gradients: Hertzmann's per-cell error threshold, or e-David's approach of scoring the fixed candidates and keeping the best. Both reuse the same rendered footprints. JAX becomes worth reinstalling only if a later spec asks for a continuous objective over mark poses.

## First experiment: drop-in replacement

**Question:** can two recipes and five scanned (or placeholder) tools turn the existing alpha plates into tool-labelled SVG that still reads as the picture?

1. Add a new provisional module beside `legacy`. Legacy files keep their provenance hashes and are not edited. Its entry point has the same shape as the current one: `alpha_stack, inkset, tools, recipes → (marks, metrics)`, plus an SVG writer. It uses Python, NumPy and Pillow only, which are already pinned.
2. Write `tools.json` with 5 tools. Use hand-drawn placeholder footprint PNGs until the owner scans the real tools, and label them `placeholder` in the SVG metadata.
3. Implement Recipe G and Recipe D (S only if G and D take less than a day). Run both on `docs/reproduction/2026-09-20/alpha/alpha_stack_float32.npz`.
4. Render the preview by stamping footprint PNGs into a per-plate coverage raster at the SVG's mm scale. Composite it with the existing `render_alpha_stack` logic so the preview and the check use one renderer.
5. Write the SVGs, a PNG of each, and a side-by-side with the current `final-svg.png`.

**Evidence to collect (a sanity check, not an objective):**

| Measure | Why |
| --- | --- |
| Marks per plate per tool; dips per plate; total drag mm | Shows how much physical work each recipe costs; this is the owner's main cost |
| Legibility error: mean absolute difference between each plate and its rendered marks, both blurred to viewing distance (Gaussian σ ≈ one cell) | The measure the current converter never reports. Compute it for the current converter too, as the baseline |
| Composite RGB RMSE vs `target` after blur, for new vs current | One number to confirm the picture still reads |
| Determinism: two runs give byte-identical SVG | Recipes must be stable to edit |
| Every mark has `data-tool`, `data-mode`, `data-dip`, `data-seq`; no footprint is scaled | Checks the output contract |
| Actual images: SVG render next to the source and the current SVG | Visual output is judged by looking at it |

**Does not prove:** physical deposition, depletion, wet mixing, a machine-ready motion order, or which recipe the owner prefers.

**Premature, do not build yet:** optimization or JAX, depletion curves, region and guide editing, Mixbox inside the preview, vpype ordering, and any change to [issue 12](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/12)'s Blender path prototype beyond noting that this decision removes Blender from the alpha→SVG step.

## Unknowns that change the plan

- **The real five tools.** Their shapes, sizes, whether they can rotate, and impressions per dip. Placeholder footprints make the first experiment runnable but not physically meaningful.
- **Which plates get which recipe.** This is the owner's aesthetic choice. The experiment should make switching a one-line edit.
- **Cell size versus viewing distance.** This sets both the Close grid pitch and the blur used for the legibility check.
- **Does ink on paper compose like the RGB `over` model?** This is not verified for dipped inks. It only matters once real scans exist.
- **Machine contract.** Axes, dip station location and file format. Until these exist, `data-seq` and `data-dip` are labels, not commands.

## Verification log

Read-only checks run on 2026-09-23. No packages were installed and no code was changed.

```text
$ python3 -c "import jax"            -> ModuleNotFoundError
$ .venv/bin/python -c "import jax"   -> ModuleNotFoundError
$ cat requirements-prototype.txt     -> numpy==1.24.3, Pillow==12.2.0, pymixbox==2.0.0
$ alpha_stack_float32.npz            -> (12, 459, 369) float32
$ grep rmse|error plotter_line_drawing_svg/*.py -> no SVG-vs-target metric
$ git -C Frida log -1                -> f42fa61 (2024-06-18); how_often_to_get_paint default 4
```

## Primary sources consulted

- Hertzmann, [Painterly Rendering with Curved Brush Strokes of Multiple Sizes](https://mrl.cs.nyu.edu/publications/painterly98/hertzmann-siggraph98.pdf) (SIGGRAPH 98) and [Stroke-Based Rendering course notes](https://www.dgp.toronto.edu/~hertzman/sbr02/hertzmann-sbr02.pdf) (SIGGRAPH 2002).
- Secord, [Weighted Voronoi Stippling](https://www.cs.ubc.ca/labs/imager/tr/2002/secord2002b/secord.2002b.pdf) (NPAR 2002).
- Schaldenbrand, McCann, Oh, [FRIDA](https://arxiv.org/abs/2210.00664) and [cmubig/Frida](https://github.com/cmubig/Frida) (GPL-3.0).
- Deussen, Lindemeier, Pirk, Tautzenberger, [Feedback-guided Stroke Placement for a Painting Machine](https://geometry.stanford.edu/lgl_2024/papers/dlpt-fgsppm-12/dlpt-fgsppm-12.pdf) (CAe 2012).
- Li et al., [DiffVG](https://people.csail.mit.edu/tzumao/diffvg/); Huang et al., [Learning to Paint](https://arxiv.org/abs/1903.04411); Liu et al., [Paint Transformer](https://arxiv.org/abs/2108.03798); Zou et al., [Stylized Neural Painting](https://arxiv.org/abs/2011.08114); Jang et al., [Gumbel-Softmax](https://arxiv.org/abs/1611.01144).
- Chuck Close: [Walker Art Center](https://www.walkerart.org/collections/artist/chuck-close/), [Met exhibition text](https://www.metmuseum.org/press-releases/chuck-close-prints--process-and-collaboration-2003-exhibitions) ([reprint](https://www.tfaoi.org/aa/4aa/4aa207.htm)), [Whitney, *Phil*](https://whitney.org/collection/works/1425), [BOMB interview, 1995](https://bombmagazine.org/articles/1995/07/01/chuck-close/).
