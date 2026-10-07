# How Blender builds evenly spaced contour toolpaths from a drawing

Research for [Establish how Blender builds evenly spaced contour toolpaths from a drawing](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/19), 2026-10-07. Its map is [issue 17](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/17).

The owner chose the route while this was being written: **the GeoSlicer add-on together with Geometry Nodes**. So this note is mostly about making that route work and where it falls short. The other two routes are kept short, as fallbacks.

This is research. It does not freeze an interface or approve a design.

**How to read it.** Every statement carries one tag:

- **[ran]** — run on this machine on 2026-10-07; the number comes from that run. Command shapes are in [How it was run](#how-it-was-run).
- **[source]** — read in the primary source linked beside it. The add-on's code and the scikit-image page I read myself; the Blender manual, release-note and source pages were read by a delegated research pass and are listed under [Sources](#sources).
- **[inference]** — reasoning from the two above. Not a measured fact.
- **[unknown]** — not settled.

## The short answer

1. **The add-on route works headless on Blender 4.3.2**, installed as an extension into a throwaway profile and called through its operator **[ran]**.
2. **Out of the box its travel direction is wrong for this plate.** It turns every closed loop counter-clockwise and lets open lines alternate. Only 39 % of the line length on the test plate had the rising ground on the left **[ran]**.
3. **A small repair tree fixes that.** It turns the add-on's toolpath mesh back into curves, flips the paths that need it, and keeps the add-on's print order. After it, 100.0 % of the length had the rising ground on the left (99.2 % on a very busy drawing) **[ran]**.
4. **Spacing is exact only with a small trick.** Asked for 0.4 mm, the add-on gave 0.3993 mm with the first line in the wrong place. Two tiny anchor triangles in the landform and its Count mode give 0.4000 mm with the first line half a bead from the drawing **[ran]**.
5. **Its real cost is that slicing is a button, not a live node.** One press takes 13 to 25 s and 1.8 GB at plate size **[ran]**. The landform before it and the curves after it stay live.
6. **If that wait becomes the problem**, a chain of ordinary nodes does the same job live in about a second. It is described under [Fallbacks](#fallbacks).

## What "the same way round" has to mean

The colour of a line comes from its travel direction. So the useful rule is **the rising ground is always on the same side of travel** (here: uphill on the left). Then the travel direction at any point is the slope direction turned a quarter turn, and colour depends only on which way the landform faces there **[inference]**.

"Counter-clockwise" is a different rule. A loop round a hill and a loop round a hollow, both counter-clockwise, have the rising ground on opposite sides. A distance landform is full of both: lines that ring a shape from outside circle a hollow, lines inside a closed shape circle a hill. Lines cut off by the plate edge are not loops at all, so "counter-clockwise" says nothing about them **[inference]**.

Whether the reference plate follows the uphill-on-one-side rule is a question for the colour model on the map, not answered here **[unknown]**.

## The test

- **Machine:** WSL2 Ubuntu, AMD Ryzen 9 7950X (32 threads), 47 GB memory. Other sessions were using it, and identical runs differed by up to about two times. Read the times as rough **[ran]**.
- **Blender:** 4.3.2 at `~/.local/opt/blender-4.3.2/blender` for everything in the add-on route. The host's 4.0.2 (`/usr/bin/blender`) and a 5.2.2 LTS build were used only for version checks.
- **Plate:** 200 by 160 mm, lines 0.4 mm apart, first line half a bead from the drawing, 1 Blender unit = 1 mm.
- **Three synthetic drawings**, no third-party images: *simple* (a ring with a smaller ring inside it, a separate blob, one open stroke; 141 levels), *dense* (400 small shapes and 200 strokes; 23 levels), *sparse* (one stroke near an edge; 403 levels).
- **Scoring:** one scorer for every route. It measures the true distance from each output point to the drawing, then reports path count, total length, how far a path strays from a single distance, and the share of line length with the rising ground on the left.

One correction to the brief: "about 400 levels" is the near-empty plate. A busy drawing has few levels (23 in the dense test). What stays the same is total length, about area divided by spacing: 79.7 to 80.0 m on the simple and sparse drawings, 71.5 m on the dense one **[ran]**.

## The add-on route, step by step

Source read at commit `817d7db` of <https://github.com/luigipacheco/fabnodes>: `__init__.py`, `slicer.py`, `gcode_python.py`, `blender_manifest.toml` and the README. It is GPL-3.0-or-later **[source]**. Nothing in the three Python files touches the network or writes files; G-code goes to a text block inside Blender **[source]**.

### 1. Install it and call it headless

```
export BLENDER_USER_RESOURCES=<a throwaway folder>
blender --command extension build --source-dir <copy of the add-on> --output-dir <out>
blender --command extension install-file -r user_default --enable <out>/GeoSlicer-0.1.0.zip
blender -b --python <script> -- <arguments>
```

- This built a 21,423-byte zip and installed it as `bl_ext.user_default.GeoSlicer`. A fresh headless Blender then had `bpy.ops.toposlice.run` **[ran]**.
- **Do not pass `--factory-startup`.** With it the add-on is not loaded **[ran]**.
- **The real profile was not touched.** Nothing under `~/.config/blender/4.3` changed during these runs **[ran]**. Without the variable, that profile loads its own add-ons at every start, so setting the variable is worth keeping for repeatable runs.
- Settings live on `scene.topo_slicer`: `target_object`, `use_modifiers`, `strategy`, `layer_mode`, `num_layers`, `max_layer_height`, `resample_length`, `align_seams`, `make_curves` ([`slicer.py` lines 636 to 727](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L636-L727)) **[source]**. The operator needs an active mesh object and returns `{'FINISHED'}` **[ran]**.

### 2. Build the landform with nodes

Grid the size of the plate → Geometry Proximity to the drawing's edges → raise each point by `distance − half a bead`. Slopes are 45 degrees, so layers one bead apart in height are lines one bead apart on the plate. This tree is live and builds in under 0.1 s at a 0.2 mm grid (801,807 points) **[ran]**. The add-on slices the evaluated mesh when `use_modifiers` is on **[source]**, **[ran]**.

**Getting the spacing exact.** In Height mode the add-on takes `ceil(height range / layer height)` layers and divides the range evenly ([lines 844 to 872](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L844-L872)) **[source]**. Asking for 0.4 mm gave 0.3993 mm, with the first line a whole step above the lowest point **[ran]**. The fix that worked:

- Join two tiny flat triangles to the landform, off the plate: one at Z = minus one bead, one at Z = `levels × bead`, where `levels` is the landform's top divided by the bead, rounded up. They pin the range. Being flat, no layer crosses them.
- Use Count mode with `num_layers = levels + 1`.
- Result: layer step 0.39998 to 0.40002 mm, first line exactly half a bead from the drawing **[ran]**. Python has to read the landform's top once to set the two numbers.

### 3. Slice: Planar strategy

How it decides direction, from the source and confirmed by running:

- **Closed loops: a flat area test.** `_ensure_ccw` reverses any closed loop whose signed area in XY is negative ([lines 158 to 175](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L158-L175)) **[source]**. Every loop comes out counter-clockwise, whichever side the hill is on. On the simple drawing: 170 loops round a hill and 107 round a hollow, all 277 counter-clockwise **[ran]**. So nested loops do **not** keep one sense relative to the uphill side.
- **Open lines: nearest end first.** An open chain is reversed when its far end is nearer to where the previous chain stopped ([lines 895 to 902](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L895-L902)) **[source]**. That saves travel and ignores the slope. On the simple drawing: 199 open lines with uphill on the left, 176 on the right **[ran]**.
- **Order:** layers bottom to top, which here means nearest the drawing first; within a layer, in the order found; each loop rotated to start near the previous layer's start ([lines 881 to 906](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L881-L906)) **[source]**.
- **Output:** a new mesh object `<object>_toolpath` in a collection called `Topology_Slices`, replaced on every run. Vertex order is print order. Points carry `tangent`, `snormal`, `path`, `layer`, `draw`, `layer_t`, `layer_h`, `seg_len`, `dist` and `role` **[source]**, **[ran]**. `tangent` is a central difference along the chain ([lines 307 to 321](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L307-L321)) **[source]**.

### 4. Bring the toolpath back into curves and repair the direction

The add-on's README says its own curve output cannot carry attributes and is for viewing only **[source]**. A node tree does better. On a Curves object:

1. **Object Info** pointing at `<object>_toolpath`.
2. **Mesh to Curve.** Each path becomes one curve and every point attribute comes along **[ran]**. Do not count on it to keep the add-on's direction: the manual says nothing about direction, and the 5.2.2 source sets it from vertex and edge numbers **[source]** ([manual](https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/mesh/operations/mesh_to_curve.html), [source file](https://raw.githubusercontent.com/blender/blender/v5.2.2/source/blender/geometry/intern/mesh_to_curve_convert.cc)). Steps 3 and 4 set the direction from the slope instead, so it does not matter.
3. **Uphill direction** from `snormal`: it leans downhill, so uphill is minus its flat part.
4. **Curve Tangent** crossed with that direction says which side the rising ground is on. **Reverse Curve** flips the paths that have it on the right. The sign must be worked out per point and then averaged per curve, not the other way round, or closed loops average to nothing **[ran]**.
5. **Sort Elements** on curves by `path` puts them back in the add-on's print order.
6. **Store Named Attribute** `tangent` from Curve Tangent. The add-on's own `tangent` is stale on every flipped path, so it is overwritten.

It ran in 0.03 to 0.04 s on about 700,000 points. Path order was kept, there was exactly one curve per path, and every loop still started at the add-on's seam point **[ran]**.

**The tree has to be pointed at the toolpath again after every run.** The add-on deletes `<object>_toolpath` and makes a new one each time, and that left the Object Info input empty after a second run **[ran]**. One line of Python after the operator call sets it back.

Loops stay as open curves whose two ends meet, because the add-on repeats the first point at the end. Welding them shut with Merge by Distance was tried and dropped: on the dense drawing it turned 10,487 paths into 10,529 curves, lost about 8,800 points and moved seams **[ran]**. If truly cyclic curves are needed, drop the repeated point and set the curve cyclic instead **[inference]**, not run.

### What it did

Blender 4.3.2, 0.2 mm grid, Count mode with anchors, repair tree without welding. All **[ran]**.

| Drawing | Levels | Slicing time | Paths | Uphill on the left, as sliced | After the repair tree |
| --- | --- | --- | --- | --- | --- |
| simple | 141 | 14.6 s | 652 | 39.5 % | 100.0 % |
| dense | 23 | 12.9 s | 10,487 | 93.1 % | 99.2 % |
| sparse | 403 | 24.7 s | 536 | 68.5 % | 100.0 % |

- **Peak memory** 1.8 GB for the whole Blender process, every drawing.
- **After the repair**, the simple drawing had all 170 hill loops counter-clockwise, 103 of 107 hollow loops clockwise, and all 375 open lines with uphill on the left. The four stragglers and the dense drawing's 0.8 % are tiny loops on ridge tops, where "uphill" has no clear answer **[ran]**, **[inference]** for the cause. The Python route scored 99.6 % on the same dense drawing.
- **Lines stray from their level** by 0.001 mm typically, 0.064 mm at the 95th percentile and 0.125 mm at worst on the simple drawing; 0.05, 0.11 and 0.18 mm on the dense one.
- **A 0.4 mm grid is four times faster** (4.0 s, 0.9 GB) and twice as loose (0.18 mm at the 95th percentile, 0.25 mm worst), and it breaks the simple drawing into 879 paths instead of 652.
- **Where the time goes** (simple drawing, 16.2 s with a profiler on): tracing contours 6.9 s, copying the mesh into arrays 5.0 s, building the toolpath mesh 1.5 s, measuring layer heights 1.0 s. Each layer scans every mesh edge in NumPy and then walks the crossed faces in a Python loop ([lines 178 to 249](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L178-L249)), so time grows with both grid size and layer count **[source]**, **[ran]**.

### Version limits

- The manifest asks for Blender 4.2.0 or later ([`blender_manifest.toml`](https://github.com/luigipacheco/fabnodes/blob/817d7db/blender_manifest.toml)) **[source]**.
- Installed as an extension, it was tested on 4.3.2 only **[ran]**.
- `slicer.py` loaded as a plain script also ran on 4.0.2 and 5.2.2 **[ran]**. But 4.0.2 has no `extension` command and no Sort Elements node, so the install step and the repair tree's order step both fail there **[ran]**.
- **4.3.2 is enough. Nothing in this route needs a newer Blender.** The 5.2.2 build was downloaded before the route was chosen and turned out not to be needed.
- **4.3 is not a long-term release.** The lines maintained today are 5.2 LTS (5.2.2) and 4.5 LTS (4.5.14); 4.2 LTS ended at 4.2.23 ([LTS page](https://www.blender.org/download/lts/)) **[source]**. Sort Elements, which the repair tree needs, arrived in 4.1 ([4.1 release notes](https://developer.blender.org/docs/release_notes/4.1/nodes_physics/)) **[source]**, so the route should also fit 4.5 LTS and 5.2 LTS **[inference]**.
- There is a hard cap of 3,000 layers ([line 24](https://github.com/luigipacheco/fabnodes/blob/817d7db/slicer.py#L24)) **[source]**. At 0.4 mm that is 1.2 m of distance, far beyond this plate.

### Where it falls short

- **Not live.** Moving a point of the drawing or changing the bead width means running the slicer again, waiting 13 to 25 s, and pointing the repair tree at the new toolpath object **[ran]**. A person pressing the add-on's own button in the sidebar would have to re-pick the object by hand; wrap the three steps in one `bpy` function instead **[inference]**.
- **Direction needs the repair tree.** Without it the plate's colours would flip between neighbouring lines and between hills and hollows **[ran]** for the directions, **[inference]** for the colours.
- **Spacing needs the anchor trick**, and Python must set two numbers before each run **[ran]**.
- **`layer_h` is not the line spacing here.** It is the 3D distance to the previous layer, reported as 0.56 to 0.66 mm on a 45 degree slope, about 0.4 times the square root of two **[ran]**. An extrusion formula built on it would over-feed. Use the bead width directly.
- **The toolpath sits on the landform**, with Z equal to the level. Flatten it, or keep it for the slight relief, in the repair tree **[inference]**.
- **Accuracy follows the grid**, 0.06 to 0.18 mm at 0.2 mm. A finer grid costs time and memory in proportion **[inference]** from the two grids measured.
- **Version 0.1.0, one maintainer, no tests in the repository** **[source]**. Pin the commit.

## Fallbacks

**Geometry Nodes only.** No Blender build tested (4.0.2, 4.3.2, 5.2.2 LTS) has a contour or slicing node: of 201, 246 and 329 node types, the only name matching iso, contour, slice, bisect, section, intersect or level is `FunctionNodeSliceString`, which cuts text **[ran]**. The manual's node index and the API class list for 4.2, 4.5 and 5.2 agree ([4.2 index](https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/index.html), [5.2 index](https://docs.blender.org/manual/en/5.2/modeling/geometry_nodes/index.html)) **[source]**. The volume grid nodes that could help are missing (Field to Grid) or hidden behind an experimental option (Grid to Mesh) before 5.0 ([5.0 release notes](https://developer.blender.org/docs/release_notes/5.0/geometry_nodes/)) and make surfaces, not lines **[source]**. A chain of ordinary nodes does it instead: Grid → Geometry Proximity → Triangulate → Dual Mesh → a band number per cell, `floor((distance − half a bead) / spacing)` → Mesh to Curve on the edges between two bands → Blur Attribute on position, three passes → snap each point onto its exact level with a second Geometry Proximity → Reverse Curve by the same uphill test → Sort Elements → store `tangent`. On 4.3.2 at a 0.2 mm grid it built the simple plate in 1.0 s and 1.7 GB, rebuilt in 0.9 to 1.0 s after moving a point of the drawing or changing the spacing, strayed 0.012 mm at worst, and had uphill on the left for 100.0 % of the length (99.6 % dense) **[ran]**. Its limits: the snap assumes height is plain distance to the drawing, the grid must be at most half the spacing, and it has no seam handling. Cutting the landform with a stack of planes through Mesh Boolean was also tried and is not usable: 13.5 s and 4.0 GB at a 0.4 mm grid for 468 points where about 200,000 belong **[ran]**; its "Intersecting Edges" output is documented for the Exact solver, but not for this use ([manual](https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/mesh/operations/mesh_boolean.html)) **[source]**. Use the chain if the 13 to 25 s button press becomes the bottleneck or live editing of the drawing matters.

**Python beside the node tree** (what the first preview uses). A raster distance transform plus a contour trace per level, run outside Blender: 0.13 s plus 0.85 s (contourpy) or 1.56 s (scikit-image) at 0.1 mm pixels and 222 MB; about 4 s on the 403-level drawing **[ran]**. Both libraries gave uphill on the left for 100.0 % of the length, open lines included, with no repair (99.6 % dense) **[ran]**. For scikit-image this is documented: with `positive_orientation='low'`, "low-valued elements are always on the left of the contour" ([`find_contours`](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.find_contours)) **[source]**; for contourpy it is observed only **[unknown]**. Lines stray 0.05 mm typically and 0.15 mm at worst, set by the pixel size **[ran]**. A million points became a Curves data-block with a per-point `tangent` in 0.04 s **[ran]**. Blender 4.3.2's own Python has none of SciPy, scikit-image or contourpy, so the step runs outside and passes a file **[ran]**. Its cost is editability: the curves are plain data, so nothing from the picture to the lines can be changed without running it again **[inference]**. Keep it as the reference to check the add-on route against, since it needs no repair.

| | GeoSlicer with nodes (chosen) | Geometry Nodes only | Python step |
| --- | --- | --- | --- |
| Blender needed | 4.2.0 **[source]**; ran on 4.3.2 | 4.1 for path order; ran on 4.3.2 | any; libraries live outside |
| Headless | yes | yes | yes |
| Time, full plate | 13 to 25 s per press | about 1 s, live | 1 to 4 s plus Blender start |
| Peak memory | 1.8 GB | 1.7 GB | 0.2 to 0.6 GB |
| Spacing | exact with the anchor trick | exact | set by pixel size |
| Uphill on the left | 39 to 93 % as sliced; 99.2 to 100 % repaired | 99.6 to 100 % | 99.6 to 100 % |
| Stays live | landform before, curves after | everything | only what comes after |
| Direction exposed as | `tangent` on curve points, after repair | `tangent` on curve points | `tangent` on curve points |

All cells **[ran]** on 4.3.2 unless tagged.

## Not settled

- **A real drawing.** All three test drawings are synthetic. The two-portraits outlines were not used.
- **The interactive loop:** pressing the button in the interface and watching the repair tree follow was not tried, only headless runs.
- **Whether the reference plate uses the uphill-on-one-side rule.**
- **Travel-saving order across a layer** for a real print. The add-on orders by layer and aligns seams; it does not plan hops between paths within a layer **[source]**.
- **The add-on on 4.2 LTS, 4.5 LTS and 5.2 as an installed extension.** Only its slicer file was run on 5.2.2.
- **contourpy's documented line direction.**

## How it was run

The scripts lived in a session scratch folder and are not in this repository. Shapes of the commands, with `<blender>` for `~/.local/opt/blender-4.3.2/blender`:

- Install: the four lines under [step 1](#1-install-it-and-call-it-headless). The add-on was copied out of its clone first and nothing was run from inside the clone.
- Add-on route: `BLENDER_USER_RESOURCES=<throwaway> <blender> -b --python route2_full.py -- <drawing.py> <out prefix> 0.2 0.4 noweld`, wrapped in `/usr/bin/time -f "%e %M"`. The script builds the landform tree, reads its top, sets Count mode, calls `bpy.ops.toposlice.run()`, builds the repair tree and reads the curves back. Add `profile` for the time breakdown.
- Node list: `<blender> -b --factory-startup --python-expr "<write the sorted names in bpy.types that start with GeometryNode or FunctionNode>"`, once per build.
- Nodes-only fallback: `<blender> -b --factory-startup --python route1_gn.py -- <drawing.py> <out.npz> 0.2 0.4 0 dual 3`.
- Python fallback: `uv run --no-project --with numpy --with scipy --with scikit-image --with contourpy python -I route3_python.py <drawing.py> <out prefix> 0.1 0.4`, then `<blender> -b --factory-startup --python route3_bpy.py -- <paths.npz>`.
- Scoring: `python3 -I evaluate.py <drawing.py> <paths.npz> 0.4`.

## Recommendation

**The GeoSlicer add-on's Planar slicer between two node trees, on Blender 4.3.2** (`~/.local/opt/blender-4.3.2/blender`). This is the owner's chosen route; the work above shows it holds once direction and spacing are repaired.

1. **Install the add-on from a copy pinned at commit `817d7db`** as an extension, into the profile the recipes run with. Keep `BLENDER_USER_RESOURCES` pointed at a project folder so runs do not depend on the personal profile.
2. **Landform tree:** Grid at 0.2 mm → Geometry Proximity to the drawing → Z = distance minus half a bead, plus the two anchor triangles. Inputs: the drawing, bead width, grid step.
3. **A short `bpy` function in `modules/blender_recipes`:** read the landform's top, set the top anchor and `num_layers`, call `bpy.ops.toposlice.run()` with Planar and Count. This is the one step that is a button.
4. **Repair tree on a Curves object:** Object Info → Mesh to Curve → uphill from `snormal` → Reverse Curve → Sort Elements by `path` → store `tangent`. Colour reads `tangent` in the same tree.

Check each build with the scorer's two numbers: share of length with uphill on the left (expect 99 % or more) and stray from each level (expect about 0.1 mm at a 0.2 mm grid).

## Sources

Accessed 2026-10-07.

- GeoSlicer (formerly Fabnodes) at commit `817d7db` — <https://github.com/luigipacheco/fabnodes/tree/817d7db> — `slicer.py` (orientation, open-chain direction, layer count, contour tracing, attributes, layer cap), `__init__.py` (registration, G-code export to a text block), `gcode_python.py`, `blender_manifest.toml` (version 0.1.0, Blender 4.2.0 minimum, GPL-3.0-or-later), `readme.md` (attribute table, curve output is view-only).
- scikit-image, `skimage.measure.find_contours` — <https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.find_contours> — `positive_orientation`.
- Blender builds used: 4.0.2 (distribution package), 4.3.2 (build date 2024-12-17), 5.2.2 LTS (build date 2026-09-15, from <https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz>, 383,295,504 bytes, checksum matched the published `blender-5.2.2.sha256`).
- Blender documentation, read by a delegated research pass, not re-opened by me: LTS status — <https://www.blender.org/download/lts/>; node indexes — <https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/index.html>, <https://docs.blender.org/manual/en/5.2/modeling/geometry_nodes/index.html>, <https://docs.blender.org/api/4.2/bpy.types.GeometryNode.html>, <https://docs.blender.org/api/5.2/bpy.types.GeometryNode.html>; Sort Elements — <https://developer.blender.org/docs/release_notes/4.1/nodes_physics/>; volume grid nodes — <https://developer.blender.org/docs/release_notes/5.0/geometry_nodes/>; Mesh to Curve — <https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/mesh/operations/mesh_to_curve.html> and <https://raw.githubusercontent.com/blender/blender/v5.2.2/source/blender/geometry/intern/mesh_to_curve_convert.cc>; Mesh Boolean — <https://docs.blender.org/manual/en/4.2/modeling/geometry_nodes/mesh/operations/mesh_boolean.html>.
- Repository context: `AGENTS.md`, `MODULES.md` and `modules/blender_recipes/MODULE.md` on `build/0.1.0`; the earlier note `docs/research/toolpath-tools.md` on `research/toolpath-tools` for reading curves back through a Curves object.
