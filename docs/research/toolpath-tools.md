# Which tools to test next for editable painting toolpaths

Research for [Compare toolpath tools and next experiments](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/11), 2026-09-20. It extends [Controlling painting paths in Blender](toolpath-controls.md), which already lists the control vocabulary and the CAM/slicer precedents; none of that is repeated here.

This is research. Nothing here approves a prototype design, freezes an interface, or selects the earlier one-region/one-guide idea.

**How to read it.** Every statement is tagged by where it comes from:

- **Verified** — read in a primary source `[S#]` or observed in a local check `[L#]`. All sources were accessed on 2026-09-20; the source list at the end gives each URL.
- **Proposed** — a design inference of this report. Not a fact about any tool.
- **Unknown** — could not be settled from a primary source or a small local check.

## The short answer

1. **Keep Blender as the editor and geometry stage, and keep it thin.** Native curves and Geometry Nodes on Blender 4.3.2 already hold everything an editor needs: drawable guides, regions, per-point tool rotation, and ordered centerlines that Python can read back. One local check changed the picture: the centerline and its rotation are only readable when the node graph lives on a **Curves** object, not on a mesh object as the current prototype does `[L4]`.
2. **Do not adopt Fabex as the engine.** It is a maintained, installable milling CAM, and its separation of operation, simulation and postprocessor is worth copying. Its tools are round cutters; nothing in its documented interface turns a tool about its own axis, which is the one freedom this machine is believed to have `[S6][S7]`.
3. **Use vpype only after construction, as a travel planner and travel viewer.** It is maintained and MIT licensed, but it flattens everything to polylines and keeps data per layer, never per path `[S9][S11]`. It cannot carry a rotation schedule, so it must never be the record of the painting.
4. **A custom placement stage is justified for one case only:** choosing positions and rotations of a fixed footprint to match a plate. Geometry Nodes has no optimizer, and no existing tool reviewed does this.
5. **An SVG cannot be the project.** It can carry units, layer order and tool labels. It has no notion of contact, travel, or execution order beyond draw order `[S14]`. A small sidecar file next to the SVG is needed.
6. **Recommended first experiment:** *one construction, two executions* — build spaced centerlines from an editable guide inside Blender, then execute the same centerlines once as a dragged brush and once as a fixed block stepped along them, and carry both through SVG + sidecar into a travel view. It is the cheapest test that needs no new algorithm, exercises the owner's edit loop, and produces the data that the other two experiments reuse.

## Local facts

All checks were read-only and unpaid. Commands are given with the user's home written as `~`.

| # | Check | Command | Result |
| --- | --- | --- | --- |
| L1 | Blender on PATH | `blender --version` | **4.0.2** (the distribution package, in `/usr/bin`). |
| L2 | The other install | `find / -maxdepth 6 -type f -name blender` then `~/.local/opt/blender-4.3.2/blender --version` | **4.3.2**, build date 2024-12-17, at `~/.local/opt/blender-4.3.2/`. It bundles Python 3.11 and NumPy 1.24.3. It is not on PATH; scripts must call it by path. |
| L3 | Node availability | `blender -b --factory-startup --python nodecheck.py` in each version; the script calls `nodes.new(<type>)` for 20 node types | **4.3.2:** Repeat zone, For Each Element zone, Points to Curves, Sample Curve, Geometry Proximity, Resample/Trim/Fillet Curve, Image Texture, Sample Nearest, Raycast, Instance on Points, Store Named Attribute, Bake, Simulation zone, Curves to Grease Pencil, Mesh Boolean all exist. **4.0.2:** For Each Element, Bake and Curves to Grease Pencil are missing. **Neither version has a curve-offset node** (`GeometryNodeOffsetCurve` does not exist). |
| L4 | Can Python read a centerline with rotation? | `blender -b --factory-startup --python curveprobe.py` on 4.3.2; a graph makes a 5-point curve, sets tilt 0.5 and stores a point attribute `tool_angle` = 1.25 | On a **mesh** host object the evaluated data is an empty Mesh — the curve is not reachable. On a **Curves** host object the evaluated data is `Curves` with 1 curve, 5 ordered points, and attributes `position`, `tilt`, `tool_angle` readable per point with the values set. |
| L5 | Bundled add-ons | same run as L3 | 4.3.2 ships `io_curve_svg` (SVG import) and no CAM or MCP add-on. The 4.3 user configuration folder holds no installed extensions. |
| L6 | Blender MCP | key names only from `~/.claude.json`; the repo `.mcp.json` and `project-sets.json`; the `mcp/` folder of the workflow repo | **No Blender MCP server is configured anywhere.** User-level servers: chrome-devtools, cloudflare-bindings, cloudflare-docs, comfy-cloud, figma, figma-desktop, gitnexus, markitdown, mcp-gateway, notion, runpod, runpod-docs, scrapecreators, scrapling. The repo configures gitnexus only; `project-sets.json` has `"mcp": []`. No Blender MCP add-on is installed (L5). |
| L7 | Python packages | `importlib.metadata.version(...)` in the repo's `.venv`; `pip list` for system Python and Blender's Python | Repo `.venv`: **pymixbox 2.0.0**, NumPy 1.24.3, Pillow 12.2.0. **vpype, Shapely, SciPy and JAX are not installed there.** System Python has NumPy, SciPy and OpenCV but no vpype, Shapely or pymixbox. Blender's Python has NumPy only. `uv`/`uvx` are installed, so a CLI tool can run in a throwaway environment without touching these. vpype was **not** run. |

What L3 and L4 mean in plain words: Blender 4.3.2 is the version to use (4.0.2 lacks two nodes that matter), spacing between passes has no ready-made node, and the adapter must read a Curves object.

## Candidate comparison

Versions, dates and licenses are from PyPI metadata, repository metadata and release pages `[S1]–[S13]`.

| Candidate | Version · last release · license | Works with local Blender? | What it is good for | What it cannot do here | Verdict |
| --- | --- | --- | --- | --- | --- |
| **Native curves + Geometry Nodes + thin bpy adapter** | Blender 4.3.2 local (released 2024-11-19; not an LTS line — current LTS are 4.2, 4.5, 5.2) `[S2]` · GPL | Yes `[L2–L4]` | **Editing** (draw/move guides and regions), **generation** (fields, repeat and for-each zones), **preview**. Per-point tilt is a built-in curve attribute `[S3]`; any named attribute survives to Python `[L4]`. | No curve-offset node `[L3]`; no optimizer or gradients (prior report); SVG add-on imports only, "limited to path geometry only" `[S5]`; whole-modifier re-evaluation, so "local" regeneration is not automatic. | **Use** as editor and geometry stage. |
| **Fabex (formerly BlenderCAM)** | 3.0.2 · 2026-01-01 · GPL-3.0-or-later `[S6]` | Installable in principle: needs Blender ≥ 4.2 and Python 3.11, which 4.3.2 has; ships its own Shapely 2.0.5, Numba and OpenCAMLib wheels; needs online access on first install `[S6]`. **Not installed or run.** | **Planning, simulation, export**: 18 strategies (parallel, cross, pocket, outline fill, spiral, medial axis, curve to path, …), path angle, distance between and along paths, climb/conventional/meander, operation chains, simulation object, a library of machine postprocessors (GRBL, LinuxCNC, Mach3, HPGL and others), scriptable operators such as `object.calculate_cam_path` `[S6][S7]`. | Cutter types are End, Ballnose, Bullnose, V-Carve, Ballcone, Laser, Custom — all round. The documented interface has no tool rotation about its own axis, no brush, pen or stamp `[S7]`. Its settings are per operation, not per painted region. | **Borrow the workflow, do not adopt.** Worth one short probe (Experiment C). |
| **vpype** | 1.15.0 · 2025-08-04 · MIT · Python ≥ 3.11, < 3.14 `[S8]`; repository active 2026-09-19 | Separate CLI; not inside Blender. Not installed `[L7]`. | **Ordering and travel preview**: `linesort` (with `--no-flip`, `--two-opt`), `linemerge`, `linesimplify`, `show --show-pen-up`, `write --pen-up` `[S10]`. Millimetre units; layers map to pens `[S9]`. | "Curved paths are not supported per se" — all geometry becomes polylines. Properties exist only globally or per layer `[S9]`; the source stores each path as a bare array with no per-path data `[S11]`. `linesort` works inside one layer only `[S10]`. | **Use downstream only**, never as the record. |
| vpype plugins | vpype-gcode 0.13.0 · 2022-10-17 · MIT `[S12]`; vpype-flow-imager · no release, last push 2022-12-04 · GPL-3.0, not on PyPI `[S13]`; hatched 0.2.0 · 2022-05-05 · MIT | Same as vpype | vpype-gcode: template text export with `x`, `y`, `dx`, indexes per segment `[S12]` — a later postprocessor, not now. flow-imager: evenly spaced streamlines (Jobard–Lefer) with min/max separation driven by image darkness, and it accepts an external flow image `[S13]`. | vpype-gcode templates have no rotation variable `[S12]`. flow-imager is unmaintained, needs a C++ compiler for its fast path, and is GPL. | flow-imager is a **reference algorithm** for spacing, not a dependency. Skip the rest. |
| **Custom placement stage** (NumPy, optionally JAX) | NumPy present `[L7]`; JAX 0.10.0 was used for the accepted solve but is not in this repo's environment `[L7]` | Runs outside Blender; reads guides/regions exported by the adapter | **Optimization**: choose position and rotation of a fixed footprint against a plate, honouring locks and ranges. The legacy DiffVG experiment optimized position, rotation, length, curvature and width — it allowed sizes a fixed tool cannot have (reproduction README). | New algorithm work. Discrete choices (how many impressions, which tool) are not smooth; gradients do not cover them (prior report). | **Justified only for fixed-impression placement** (Experiment B). |
| Shapely (only if needed) | 2.1.2 · 2025-09-24 · BSD-3-Clause `[S15]` | Not installed `[L7]` | `offset_curve` gives a line at a signed distance with round/bevel/mitre joins `[S15]` — the missing offset node, and a way to *measure* clearance independently of whatever generated the paths. | One more dependency. | **Add only if** Experiment A shows spacing cannot be built or measured natively. |

Not shortlisted: DiffVG (no releases, last push 2025-05-17, Apache-2.0 `[S16]`) — it already exists in the legacy lineage and allows free stroke sizing, which a fixed tool does not. Clipper2 and pyclipper overlap with Shapely for this need. Grease Pencil is reachable from Geometry Nodes in 4.3 `[S4]` but adds nothing the Curves object does not already give.

### Who does what

| Responsibility | Native Blender | Fabex | vpype | Custom stage |
| --- | --- | --- | --- | --- |
| Edit guides and regions | yes | uses Blender's | no | no |
| Generate paths from rules | yes (to be built) | yes, milling rules | a few generators | no |
| Optimize against a target | no | no | travel only | yes |
| Preview coverage | yes | simulation of material removal | line view | raster check |
| Plan order and travel | no | yes, per operation | yes, per layer | no |
| Export | through adapter | G-code postprocessors | SVG, HPGL, G-code plugin | no |

## Construction approaches

The painting is a portrait built on a diagonal lattice of diamond cells, each holding nested loops of colour; the dark plates (black, blue-black, sepia) carry the glasses, nostrils and moustache, and the light plates carry scattered cell rings. The examples below use that structure.

| Approach | Kind | What the owner controls | Coverage fidelity | Local regeneration | Spacing / clearance | Edits preserved? | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1. Rule-placed fixed impressions** — candidate sites on a lattice; keep a site where the plate is dark enough; rotation from the nearest guide | Procedural | lattice pitch and angle, keep threshold, rotation source, region masks | Coarse: one footprint is all-or-nothing, so tone comes only from how many sites are kept | Whole graph re-evaluates; restrict by giving each region its own object | Guaranteed only on the lattice; not between rotated neighbours | Guides and masks yes; individual impressions no | Low; one pass, no loop |
| **2. Guide-following paths** — trace lines along a direction taken from guides, stop at region edges, keep passes a brush-width apart | Procedural | guides, how far a guide's influence reaches, spacing as a function of plate darkness, length limits, stop rule | Good where tone maps to spacing; poor for isolated small shapes | Same as above | **Must be built** — no offset node `[L3]`; the known method is evenly spaced streamlines with a separation test `[S13]`; cost inside a Repeat zone is unknown | Guides yes; a hand-moved path is lost unless stored as a pinned override | Medium to high; iterative |
| **3. Contour / offset fill** — threshold a plate into shapes, fill each shape with passes parallel to its outline | Procedural | threshold, step-over, number of rings, start side, which shapes | Follows plate shapes closely; direction is dictated by the shape, guides have little say | Naturally local: one shape, one fill | Guaranteed by construction if the offset operation is exact — Shapely `offset_curve` `[S15]` or Fabex pocket/outline fill, which itself uses Shapely `[S6]` | Shapes yes; the fill is fully derived | Low to medium |
| **4. Solver-placed fixed impressions** — search positions and rotations that best rebuild a plate from one fixed footprint | Optimization | which variables are free, locked, ranged or merely preferred; overlap limit; impression budget | Best available for a fixed tool, and it is *measured* | Re-solve only the edited region if the objective is evaluated per region | Enforced as a hard constraint in the search, or reported as violations | Locks are the mechanism: a pinned impression stays | Highest; depends on impression count |
| **5. Direct editing** — owner draws or moves a path or an impression by hand | Direct | everything about that one mark | Whatever the owner draws | Trivial | None unless checked afterwards | Yes, if stored as source geometry rather than output | None |

**Values, locks, ranges, preferences.** The same slider can mean four things, and the experiment must say which:

| Variable | As a value | As a lock | As a range | As a solver preference |
| --- | --- | --- | --- | --- |
| Tool rotation | "45° everywhere" | "these impressions stay at 45°" | "within ±15° of the guide" | "prefer the guide direction, pay a penalty to leave it" |
| Spacing between passes | "2 mm" | — | "between 1.5 and 4 mm, set by plate darkness" | "as even as possible" |
| Position of an impression | hand-placed | pinned | "inside this cell" | "near the lattice site" |
| Order / direction | fixed list | "this stroke runs downward" | "any order within this plate" | "shortest travel" |
| Footprint size | **a fixed fact of the tool — never a free variable** | | | |

### Editing examples on this painting

*Fixed impressions.*

1. **Follow the lattice, then break it at the glasses.** A guide line is laid along one diagonal of the diamond lattice. Approach 1 places a fixed diamond block at each lattice site on the black plate with rotation taken from the guide, so blocks sit square to the cells. The owner then draws a closed guide around the left lens rim and marks the lens as a region where rotation follows the rim instead. Only impressions inside the lens region should turn; the count elsewhere must not change. With approach 4 the same edit becomes "rotation within ±15° of the rim" and the solver reports how much plate error that range costs compared with a free rotation.
2. **Protect the highlight in the eye.** A small region over the pale highlight inside the left lens is marked "no contact". Because a block has area, the test is on the whole footprint, not its centre: any block whose outline enters the region is dropped or moved. The visible result is a ring of blocks that stops a footprint-width short of the highlight.
3. **Pin one block by hand.** The owner drags a single impression onto the dark of a nostril and pins it. Regenerating the rest must leave it exactly there, and the neighbours must respect the overlap limit against it.

*Continuous paths.*

4. **Bend the moustache.** On the sepia plate, the owner draws one guide sweeping from the nose down through the moustache. Approach 2 traces passes along it, closer together where the plate is dark. Moving the guide's middle handle should re-flow the moustache passes and leave the cheek passes untouched. What to look at: whether spacing stays within its stated range where the lines converge.
5. **Trace the cell rings.** The rose and orange plates are mostly thin rings inside lattice cells. Approach 3 turns each ring into one closed pass down its middle, which is closer to how the original was painted than hatching is. The owner's control is the threshold that decides which rings exist and the side each ring starts from.
6. **Turn a flat brush through a curve.** Along the lens rim the path tangent turns through a full circle. The owner chooses whether the brush's long axis stays square to the path (a value), is held at the lattice angle (a lock), or may turn no faster than some rate (a range). The rotation is stored per point on the centerline, separate from the path itself, so the same path can be replayed under each choice.

## Data and integration

### Minimum information to carry between stages

Proposed; nothing here is a frozen interface.

| Item | Why it is needed | Where it lives today |
| --- | --- | --- |
| Units and page size in millimetres; one origin and axis direction | every later stage depends on it | SVG (1 Blender unit = 1 mm convention) |
| Ordered plate list: ink id, label, colour, paint order | paint order is part of the image | `alpha/metadata.json`, and as SVG group order |
| Tool identity per path or impression, pointing to a tool record: footprint outline in mm, reference point, allowed rotation | a footprint is a physical fact, not a style | nowhere yet |
| Per path: ordered points, contact on/off, direction locked or not | tells a drag from a travel move | nowhere yet |
| Per point or per impression: tool rotation in page coordinates | the machine's one assumed extra freedom | nowhere yet; carrier verified `[L4]` |
| Provenance: which region, which guide, which rule, pinned or derived | lets a regenerate keep hand edits | nowhere yet |
| Constraints used: clearance, overlap limit, spacing range | lets a reviewer re-check the output | nowhere yet |

### What an SVG can and cannot hold

Verified: SVG allows `g` groups, `title`/`desc`/`metadata`, and `data-*` attributes on elements; it defines only document order and paint order, and has no concept of a tool, contact, travel, or a schedule `[S14]`.

| Can live in the SVG | Must live beside it |
| --- | --- |
| millimetre units and page size; one group per plate in paint order; path geometry (centerline *or* footprint outline — say which); a tool label per group; ids that link each path to a sidecar record | per-point rotation; contact and travel; execution order when it differs from draw order; direction locks; tool records; constraints; provenance; anything needed to regenerate |

Two warnings follow from verified tool behaviour. Blender's SVG add-on only imports, and only path geometry `[S5]`, so an SVG cannot be reopened as an editable recipe. vpype keeps only attributes that are common to a whole layer, as layer properties `[S9]`, so per-path `data-*` values should be expected to vanish on a vpype round trip. **Proposed:** the `.blend` file is the editable project; SVG + one JSON sidecar is the exported snapshot; the path `id` is the join key; vpype reads a copy and returns an order, never the geometry of record.

### Mixbox, for comparison only

Verified: pymixbox 2.0.0 (uploaded 2022-09-20, CC BY-NC 4.0, commercial use needs a separate licence) is installed in the repo environment `[S17][L7]`. Its API is `lerp`, `rgb_to_latent`, `latent_to_rgb`; several colours are mixed by weighting their latent vectors and decoding once `[S17]`. The existing diagnostic already does this over the RGB-solved plates.

**Proposed use:** after any experiment, rasterize the footprints per plate into coverage images, then compose them twice in paint order — once with the baseline RGB rule, once through Mixbox latents — and show both beside the accepted composite. That compares *predicted colour of the constructed marks* under two models. It does not re-solve plates, does not calibrate real paint, and does not change what an SVG viewer shows. The RGB baseline stays the reference. The non-commercial licence is a limit the owner should know before Mixbox becomes more than a diagnostic.

### How the agent should author graphs: MCP or direct bpy

| Route | Version · licence | Needs | Works here today? | Limits |
| --- | --- | --- | --- | --- |
| **Direct bpy, headless** (`blender -b --python`) | Blender 4.3.2 | nothing new | **Yes** — L3 and L4 built node trees, evaluated them and read results this way | No live viewport; the agent sees results only through files it renders or exports. Deterministic and scriptable, so it fits the repo's checks. |
| **Official Blender Lab MCP server** | v1.0.3 · 2026-09-11; first release 2026-04-27 `[S18]` | "Blender 5.1 or newer"; an add-on plus a separate server process `[S18]` | **No** — local Blender is 4.0.2 and 4.3.2 `[L1][L2]`; not installed `[L6]` | Labelled a Lab project. Its page warns that it "will execute LLM generated code in Blender without any guards" and recommends a virtual machine or a system without sensitive data `[S18]`. Background-mode support is not stated. |
| **MCP for Blender** (third-party, formerly `blender-mcp`) | 2.0.0 on PyPI · 2026-09-16 · MIT `[S19]` | Blender 3.0+, Python 3.10+, `uvx`, an add-on, and a **running Blender window** in which the user presses "Start MCP Server" `[S19]` | **No** — not installed or configured `[L5][L6]`. Version-compatible with 4.3.2. | Runs arbitrary Python in Blender; its socket "has no authentication or encryption"; telemetry is on by default and must be switched off; one client at a time `[S19]`. The machine is reached over SSH, so a live Blender window is not a given. |

**Proposed:** author and check graphs with direct bpy now. It is the only route that works today, it needs nothing installed, and it leaves reproducible scripts. An MCP connection would add one thing — the agent seeing and adjusting the owner's *open* session — and that only matters once the owner is editing live. It is an owner decision because it means installing an add-on, accepting unguarded code execution, and (for the official server) moving to Blender 5.1 or later, which would also mean re-checking the prototype on a new version.

## Experiments

All three use the same recovered plates (`docs/reproduction/2026-09-20/alpha/`, 12 inks, 369 × 459 px) and the same crop: the left lens of the glasses and the cheek below it, on the **black** and **sepia** plates. Each is a few days of agent work at most and throws its code away. They differ in *who decides where marks go* — a rule, a solver, or an existing CAM — not in how the result looks.

### A. One construction, two executions *(recommended first)*

- **Uncertainty answered:** Can native Geometry Nodes build guide-following centerlines with a stated spacing range at a speed the owner can edit with, and does a centerline with tool rotation survive the trip to a travel planner? Secondary: does stepping a fixed block along those same lines give a usable fixed-impression result without any solver?
- **What is built:** a node graph on a Curves object `[L4]`: guides → direction → traced passes with a separation test → per-point `tool_angle`. Two read-outs of the same centerlines: (1) *dragged* — a fixed-width brush outline swept along each pass; (2) *stepped* — one fixed footprint placed every footprint-length along each pass, turned to `tool_angle`. A bpy adapter writes a centerline SVG in mm, a footprint SVG, and one JSON sidecar. vpype, run through `uvx`, orders a copy with `linesort --no-flip` and shows travel `[S10]`.
- **What the owner edits:** one guide through the lens rim and one through the cheek; one region mask; the spacing range; whether rotation follows the path, holds the lattice angle, or is rate-limited. No Python.
- **Artifacts to inspect:** the `.blend`; before/after images of moving a guide handle; centerline and footprint SVGs; the travel view; RGB and Mixbox compositions of the rasterized footprints.
- **Evidence (measured by the adapter, independently of the graph):**
  1. smallest distance between any two centerlines ≥ the stated minimum — pass/fail;
  2. after moving the cheek guide, the share of lens-region points that moved — should be zero;
  3. time to re-evaluate after one guide move, recorded, with 2 s proposed as the line between "editable" and "not";
  4. every exported point has a rotation, and the sidecar re-joins to the SVG by id with no orphans;
  5. coverage error of each read-out against the plate, reported, not judged.
- **Dependencies:** Blender 4.3.2 (present); vpype 1.15.0 in a throwaway `uvx` environment (small, MIT, first run not yet tried `[L7]`).
- **Deliberately does not prove:** that the fill is the best one; anything about paint, pressure, loading or machine motion; that vpype's order is safe for wet paint; that stepped impressions are as good as solved ones (that is B).

### B. Solved placement of one fixed footprint

- **Uncertainty answered:** How well can one fixed-size footprint with rotation as its only freedom rebuild a plate, and what does each kind of owner control cost in plate error — rotation locked to a guide, ranged around it, preferred, or free?
- **What is built:** a small NumPy search outside Blender. Start from lattice sites; greedily add, move and turn impressions to lower the difference between rasterized footprint coverage and the plate; overlap limit and "no contact" regions are hard constraints. Guides and regions come from Blender through the same adapter; results return as instances for viewing.
- **What the owner edits:** the footprint outline (one real tool, drawn in mm); the rim guide; the protected highlight; the rotation mode per region; one pinned impression.
- **Artifacts:** one error map per rotation mode; impression counts; the footprint SVG and sidecar; RGB and Mixbox compositions.
- **Evidence:** plate error per mode in one table; zero overlap and zero protected-region violations; the pinned impression unmoved; after a regional edit, the number of impressions that changed outside the region; solve time.
- **Dependencies:** NumPy and Pillow (present). JAX only if greedy search proves too weak, which would be a finding.
- **Deliberately does not prove:** continuous paths; that greedy is the right solver; physical coverage — the footprint is all-or-nothing digital coverage.

### C. Borrowed CAM probe

- **Uncertainty answered:** How much of the wanted workflow does a mature CAM add-on already give — spacing that is guaranteed, region limits, ordering, simulation, export — and exactly where does it stop for a turning tool?
- **What is built:** nothing new. Install Fabex 3.0.2 into an isolated copy of Blender 4.3.2's user settings; threshold the black plate into curve shapes; run *pocket*, *outline fill* and *parallel* with a limit curve over the crop, cutter diameter set to the brush width; export through the simplest postprocessor and read the generated path objects back with bpy.
- **What the owner edits:** Fabex's own panel — path angle, distance between paths, distance along paths, movement type, the limit curve.
- **Artifacts:** generated path objects, the simulation object, the exported file, screenshots of the panels.
- **Evidence:** measured pass spacing against the setting; whether a limit curve truly bounds the tool's edge or only its centre; whether the path objects can be read as ordered curves; a written list of settings with no equivalent for a turning brush.
- **Dependencies:** a Fabex install (GPL-3.0-or-later; bundles Shapely, Numba and OpenCAMLib; needs online access once) `[S6]`. This is the heaviest install of the three and needs the owner's yes.
- **Deliberately does not prove:** anything about rotation, impressions or per-region rules — Fabex has none of these to test `[S7]`. A good result means "copy these ideas", not "adopt Fabex".

### Why A first

1. It rests entirely on capabilities verified locally and needs no new algorithm, so a failure points at the tool, not at the idea.
2. It is the only one that tests the owner's actual request — editing how paths are constructed, by hand, without scripts.
3. Its adapter, SVG + sidecar and measurements are exactly what B and C need; doing B first would mean building them anyway without testing them on paths.
4. Its failure is informative: if spacing cannot be held or re-evaluation is too slow, that is the evidence for moving construction into an outside stage (Shapely, or B's solver), and for running C to see what a CAM does instead.
5. It covers both fixed impressions and continuous paths in one construction, so the owner can compare them before choosing which deserves a solver.

B should follow if the stepped read-out in A looks promising but its plate error is poor. C is optional and cheap to defer.

### Decisions needed before building A

1. **One real tool for each read-out** — a brush width in mm for the dragged case and a footprint outline in mm for the stepped case. Guesses are acceptable if labelled as guesses.
2. **Agree the crop and the two plates** (proposed: left lens and cheek; black and sepia).
3. **May vpype be run through `uvx`** as a throwaway tool, outside the repo's pinned environment?
4. **Is a sidecar JSON beside the SVG acceptable** as the experiment's carrier for rotation and contact, with no promise it becomes the final format?
5. **Headless only for now?** That is, the agent authors with direct bpy and the owner opens the saved `.blend`; no MCP install.

## Unknowns and sequence

**Researchable, still open**

- Whether an evenly spaced tracing loop inside a Repeat zone is fast enough on this crop. Only a measurement will say; A measures it.
- Whether vpype's SVG writer keeps path `id` attributes. If not, the adapter rejoins by order. Not checked, because vpype was not run.
- Whether Fabex's limit curve bounds the cutter's edge or its centre, and whether its `drag_knife` postprocessor carries any notion of tool heading. The file exists in the repository `[S6]`; it was not read.
- Whether Blender 5.x changes any node used here. The prototype is pinned to 4.3.2, which is not an LTS line `[S2]`; 4.5 LTS or 5.2 LTS would be the natural targets if the owner wants the official MCP server.

**Hardware facts only the machine can answer**

- Whether the tool can turn while in contact, how fast, and through what range.
- Whether there is any lift axis at all, and therefore whether "travel" exists as a separate state.
- The real footprints, and whether a brush's contact width is stable enough to treat as fixed.
- Whether paint order across plates is forced by drying.

**Owner preferences**

- Whether the diagonal lattice of the source painting should be a visible, editable structure or just one possible guide.
- Whether hand-pinned marks are wanted at all, or only guides and regions.
- Whether the non-commercial Mixbox licence is acceptable beyond a diagnostic.

**The only missing facts that would change the recommendation**

- If the tool **cannot turn while in contact**, the dragged read-out in A loses its rotation control and B becomes the better first experiment.
- If the owner wants the agent to work **inside a live session from day one**, an MCP install and possibly a Blender upgrade come before A.
- If a Fabex install is unwelcome, C drops out and nothing else changes.

**Sequence after A** (proposed, not tickets)

1. Run A; the owner edits the guides and reads the five measurements.
2. Decide from the evidence: is construction staying inside Blender, or moving to an outside stage?
3. Run B if fixed impressions matter and A's stepped result is not good enough; run C only if planning and simulation ideas are still wanted.
4. Write down the machine facts above as they become known.
5. Only then specify: tool records, the project-versus-export data contract, the control layers from the earlier report, and acceptance tests drawn from the measurements that proved useful.

## Could not be verified from a primary source

- Fabex on Blender 4.3.2 specifically. The manifest says Blender ≥ 4.2 and the release notes require Python 3.11 `[S6]`; both hold locally, but it was not installed.
- Whether the official Blender Lab MCP server runs against a background (windowless) Blender. Its page does not say `[S18]`; its licence was also not stated on the page read.
- vpype's behaviour on per-path `data-*` attributes. The documentation says only layer-common attributes are kept `[S9]`; loss of per-path values is an inference from that and from the source `[S11]`.
- Support status of Blender 4.3. The releases page lists it as a non-LTS release and gives no end date `[S2]`.
- The Blender 4.3 manual page for the For Each Element zone could not be found at the guessed URLs; the node's existence rests on the 4.3 release notes `[S4]` and the local check `[L3]`.
- Interactive speed of any of this. Nothing was benchmarked.

## Sources

All accessed 2026-09-20.

- **S1** PyPI JSON metadata for each package named, `https://pypi.org/pypi/<name>/json` — versions, upload dates, licences, Python requirements.
- **S2** Blender release list — <https://www.blender.org/download/releases/> — 5.2 LTS (2026-07-14), 4.5 LTS (2025-07-15), 4.2 LTS (2024-07-16); 4.3 released 2024-11-19, not LTS.
- **S3** Blender 4.3 manual, Set Curve Tilt node — <https://docs.blender.org/manual/en/4.3/modeling/geometry_nodes/curve/write/set_curve_tilt.html> — tilt is an angle per control point that turns the curve normal about the tangent.
- **S4** Blender 4.3 release notes, Geometry Nodes — <https://developer.blender.org/docs/release_notes/4.3/geometry_nodes/> — For Each Element zone added; Grease Pencil handled as layers of curves.
- **S5** Blender 4.3 manual, SVG add-on — <https://docs.blender.org/manual/en/4.3/addons/import_export/curve_svg.html> — "allows only importing and is limited to path geometry only". Also Bake node — <https://docs.blender.org/manual/en/4.3/modeling/geometry_nodes/geometry/operations/bake.html> — baked data "is not considered to be an import/export format".
- **S6** Fabex source and release — <https://github.com/vilemduha/blendercam> (`fabex/blender_manifest.toml`, `fabex/strategies/`, `fabex/operators/path_ops.py`, `fabex/post_processors/`) and <https://github.com/vilemduha/blendercam/releases/tag/3.0.2> — version 3.0.2 published 2026-01-01; `blender_version_min = "4.2.0"`; GPL-3.0-or-later; bundled wheels; Python 3.11 requirement; strategy and postprocessor file lists; operator ids.
- **S7** Fabex documentation, interface — <https://spectralvectors.github.io/blendercam/interface.html> — strategies, path angle, distances, movement types, cutter types, chains, simulation.
- **S8** vpype on PyPI and GitHub — <https://pypi.org/project/vpype/>, <https://github.com/abey79/vpype> — 1.15.0, 2025-08-04, MIT, Python ≥ 3.11, < 3.14; last push 2026-09-19.
- **S9** vpype fundamentals — <https://vpype.readthedocs.io/en/latest/fundamentals.html> — polylines only; layers; CSS-pixel default unit with mm supported; global and layer properties; `svg_`-prefixed layer properties.
- **S10** vpype command reference — <https://vpype.readthedocs.io/en/latest/reference.html> — `read`, `write --pen-up --restore-attribs`, `linesort --no-flip --two-opt`, `linemerge`, `linesimplify`, `show --show-pen-up`.
- **S11** vpype source, `vpype/model.py` — <https://github.com/abey79/vpype/blob/master/vpype/model.py> — `LineCollection` stores `list[np.ndarray]`; metadata attaches to the collection and the document.
- **S12** vpype-gcode — <https://github.com/plottertools/vpype-gcode> — 0.13.0, 2022-10-17, MIT; template variables per layer, line and segment. Plugin list — <https://vpype.readthedocs.io/en/latest/plugins.html>.
- **S13** vpype-flow-imager — <https://github.com/serycjon/vpype-flow-imager> — GPL-3.0, no releases, last push 2022-12-04; evenly spaced streamlines after Jobard and Lefer; `--flow_image`, `--min_sep`, `--max_sep`.
- **S14** SVG 2, document structure — <https://www.w3.org/TR/SVG2/struct.html> — `g`, `title`, `desc`, `metadata`, `data-*`; no tool, contact or schedule concept.
- **S15** Shapely — <https://shapely.readthedocs.io/en/stable/reference/shapely.offset_curve.html>, <https://pypi.org/project/shapely/> — 2.1.2, 2025-09-24, BSD-3-Clause; signed-distance offset with join styles.
- **S16** DiffVG — <https://github.com/BachiLi/diffvg> — Apache-2.0, no releases, last push 2025-05-17.
- **S17** Mixbox — <https://github.com/scrtwpns/mixbox/blob/master/python/README.md>, <https://pypi.org/project/pymixbox/> — pymixbox 2.0.0, 2022-09-20, CC BY-NC 4.0; `lerp`, `rgb_to_latent`, `latent_to_rgb`.
- **S18** Official Blender Lab MCP server — <https://www.blender.org/lab/mcp-server/>, <https://projects.blender.org/lab/blender_mcp/releases> — v1.0.3 on 2026-09-11, v1.0.0 on 2026-04-27; Blender 5.1 or newer; unguarded code execution warning.
- **S19** MCP for Blender — <https://github.com/ahujasid/mcp-for-blender>, <https://pypi.org/project/mcp-for-blender/> — 2.0.0, 2026-09-16, MIT; Blender 3.0+; socket add-on on port 9876 without authentication; arbitrary code execution; telemetry on by default.
- Repository evidence: `docs/reproduction/2026-09-20/README.md`, `docs/prototypes/blender-recipes/README.md` and `modules/blender_recipes/` on `build/0.1.0`.
