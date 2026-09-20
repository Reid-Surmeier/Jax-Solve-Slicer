# Painting toolpath options

Research for [Research tools and construction approaches for the next painting-toolpath prototype](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/11), dated **2026-09-20**.

This is a research report. It does not select a production architecture, change a module interface, or build the next prototype.

## Executive finding

Use native Blender curves and Geometry Nodes as the editable authoring and preview surface, with a thin `bpy` adapter that creates graphs, reads evaluated geometry, and writes a declared export. Keep the adapter and node graph deterministic. Treat the physical footprint as a fixed asset with an explicit allowed orientation set; do not expose width or length scaling unless the tool is later calibrated to support it.

Fabex is useful as a source of CAM vocabulary and as a later comparison for machine-path concerns, but it is aimed at CNC milling and G-code rather than image-guided paint deposition. vpype is a good downstream utility once a continuous, line-based representation exists: it can merge, simplify, reorder, inspect, and write SVG, but it is not a fixed-impression generator or a lossless recipe store. A custom guided stage is justified for the part neither tool owns: placing fixed footprints against an alpha target while respecting guides, regions, orientation limits, and eventually travel constraints.

The first learning experiment should be a small fixed-footprint placement graph: one recovered alpha plate, one actual digital footprint, one editable guide, one exclusion or override region, and two construction controls. Show centerlines, contact footprints, and raised travel separately. This tests the requested editing model while avoiding an uncalibrated optimizer. A continuous guide-following experiment should follow it using the same plate and review contract.

## Starting evidence and scope

The accepted baseline is the recovered RGB alpha solve and layered SVG. The legacy reproduction says its marks are filled paths whose count and dimensions respond to alpha coverage, with per-layer base angles and deterministic variation; it does not establish calibrated fixed-tool contact. The preserved Blender prototype uses an image-sampled point grid, footprint instances, realized planar geometry, and filled SVG polygons. Its own report says it is not a centerline, motion, or paint-calibration result. See the [baseline report](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/blob/abda76e26c217117c8b3b22e85363bd2df907ddf/docs/reproduction/2026-09-20/README.md), [Blender prototype report](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/blob/build/0.1.0/docs/prototypes/blender-recipes/README.md), and [control research](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/blob/186f3d7/docs/research/toolpath-controls.md).

Verified repository facts from `AGENTS.md`, `MODULES.md`, `CONTEXT.md`, issue 1, issue 10, and issue 11:

- The current modules are preserved legacy Python, Blender-hosted Python, review, and testing. Blender is the host-language exception; no TypeScript wrapper is required for this prototype.
- A Blender 4.3.2 run is part of the preserved prototype evidence, but the local binary inspected for this report is `/usr/bin/blender` 4.0.2. Version-specific behavior must therefore be checked in the pinned prototype environment before implementation.
- The owner needs control over how construction works: guides, regions, path rules, fixed impressions, and continuous paths are all in scope. Randomness is not a substitute for editability.
- Hardware axes, dimensions, tool library, contact behavior, pressure, paint loading, and motion-controller format are unspecified. Claims below about physical deposition or machine readiness are consequently proposals or limits, not verified facts.

## Candidate tools and responsibilities

| Candidate | What it is good at | What it does not settle here | Recommendation |
| --- | --- | --- | --- |
| Native Blender curves + Geometry Nodes + thin `bpy` adapter | Editable guides and regions, procedural fields, repeated fixed geometry, visual comparison, saved `.blend` recipe, evaluated export | General image-target optimization, robust 2D clipping/clearance, calibrated deposition, machine scheduling | **Use first** |
| FabexCNC | Existing CAM strategies, machine and operation properties, collision/simulation concepts, G-code output | Paint-specific coverage, fixed brush footprints, alpha-target fitting, the project’s unspecified machine contract | Read and compare; do not add yet |
| vpype | SVG/line ingestion, layer-aware processing, line merge/sort/reloop/simplify, plotting preview, SVG and HPGL output | Filled footprint placement, guide semantics, physical contact, arbitrary SVG round-trip, image-target solving | Optional postprocessor after centerlines exist |
| Custom guided or optimized stage | Explicit footprint placement, alpha objective, guide penalties, region constraints, fixed orientation choices, a later travel planner | Requires a defined forward model, constraints, objective, and evaluation data | Add only for the missing problem |

### Native Blender route

Blender fields are functions evaluated in the context of geometry elements, so a graph can compute per-point selection, direction, length, or rotation from position, image values, and guide data. The official [Fields documentation](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/fields.html) describes this per-element evaluation model. `Instance on Points` places a reference to geometry at points and accepts per-point selection, instance index, rotation, and scale; that is directly useful for fixed impressions, provided scale is locked or deliberately constrained. See the [official node documentation](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/instances/instance_on_points.html).

For continuous paths, native nodes provide the ingredients rather than a finished paint planner. `Resample Curve` creates uniformly spaced poly-spline points in count or approximate-length mode; `Curve to Mesh` sweeps a profile along a curve; `Trim Curve` changes curve extents; and `Points to Curves` assembles points using explicit curve grouping and order. These are enough to make an editable guide-following demonstrator, but they do not by themselves choose a good path order, solve a mask-clearance problem, or minimize travel. Sources: [Resample Curve](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/resample_curve.html), [Curve to Mesh](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/curve_to_mesh.html), [Trim Curve](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/trim_curve.html), and [Points to Curves](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/point/points_to_curves.html).

The adapter should create or update the node group and expose only declared controls: source alpha image, tool object or collection, guide object, region objects, units, plate identity, orientation mode, fixed footprint choice, spacing or step, coverage threshold, and path/order preview switches. The owner can edit curve control points and region geometry using Blender; the graph recomputes dependent geometry. Keep centerlines and realized contact footprints as separate outputs so a filled SVG cannot be mistaken for a motion path.

Direct `bpy` is the reliable baseline for authoring because the repository already runs Blender scripts through the native command line and exports evaluated scene geometry. The Blender Python API exposes geometry node trees and node-group interfaces, and Blender’s Python examples show retrieving evaluated geometry through a dependency graph: [GeometryNodeTree API](https://docs.blender.org/api/current/bpy.types.GeometryNodeTree.html) and [evaluated geometry example](https://github.com/blender/blender/blob/main/doc/python_api/examples/bpy.types.GeometrySet.0.py). The adapter should remain a small reproducible wrapper around this source-of-truth graph.

### FabexCNC

Fabex’s own documentation says it creates toolpaths and G-code for CNC machines, can generate paths from 3D objects or 2D depth images, and can simulate calculated paths. Its code overview lists machine and movement properties, collision utilities, path strategies, and G-code import/export. Sources: [Fabex overview](https://spectralvectors.github.io/blendercam/) and [code overview](https://spectralvectors.github.io/blendercam/overview.html).

That makes Fabex relevant as a reference for separating stock/tool/machine/operation data and for inspecting established strategies such as parallel, pocket, outline-fill, medial-axis, and curve-to-path. It does not show that an alpha plate can drive calibrated paint deposition or that a fixed brush footprint can be treated like a milling cutter. Its current repository is GPL-3.0, and its release page identifies FabexCNC 3.0.2; the documentation says current Fabex is a Blender extension for “v4.21 and later” and warns that its packaged dependencies target Python 3.11. Sources: [Fabex repository](https://github.com/vilemduha/blendercam), [GPL-3.0 license](https://github.com/vilemduha/blendercam/blob/master/LICENSE), [3.0.2 release](https://github.com/vilemduha/blendercam/releases/tag/3.0.2), and [installation requirements](https://spectralvectors.github.io/blendercam/install.html). The local Blender 4.0.2 binary is below that stated current extension range, so no compatibility claim should be made without a separate pinned Blender check.

Fabex is therefore a later adapter or comparison, not a dependency for the next learning experiment. Its GPL license also deserves an explicit distribution decision before incorporating code or bundling it.

### vpype

vpype is a line-oriented command-line and Python library for plotter vector graphics. The maintained repository documents SVG input/output, multi-layer data, a viewer, path statistics, plug-ins, and plotting optimization; its cookbook demonstrates `linemerge`, `linesort`, `reloop`, `linesimplify`, and `write`. Sources: [vpype README](https://github.com/abey79/vpype), [cookbook](https://vpype.readthedocs.io/en/latest/cookbook.html), and [1.15.0 release](https://github.com/abey79/vpype/releases/tag/1.15.0). The repository is MIT-licensed: [license](https://github.com/abey79/vpype/blob/master/LICENSE).

The useful division is downstream: Blender or a custom stage emits open centerlines with layer and tool metadata; vpype can inspect and reorder line geometry to reduce raised travel, simplify sampled curves, and produce a plotter-oriented SVG. `linesort` is a travel heuristic, not a paint-contact planner. vpype’s own README warns that it converts curves to line segments and only partially uses SVG metadata, so it is unsuitable as the recipe’s canonical store or as a lossless round-trip layer. That limitation is a primary-source statement, not an inference: [vpype limitations](https://github.com/abey79/vpype#what-vpype-isnt).

The current checkout has no `vpype` executable or importable module. It should remain an optional experiment dependency, outside the prototype baseline, until the output contract is clear.

### Custom guided or optimized stage

A custom stage is justified for fixed impressions because the project needs to choose positions and orientations for a known footprint against an alpha target. The forward model would rasterize or otherwise evaluate the union/overlap of footprints; the stage could then rank candidate placements using target coverage, guide agreement, region permissions, overlap, and travel penalties. This is a proposal, not an existing library capability.

Do not call this an optimizer until the objective and variables are written down. A control can be a fixed value, a locked value, an allowed range, an initial guess, or a soft preference. For example, a guide angle can be enforced exactly, used to seed a search, or penalized when a placement departs from it. JAX documents automatic differentiation and `value_and_grad`, and its `minimize` API accepts a differentiable scalar objective and initial parameters; that makes the existing JAX lineage a possible future home for a compatible forward model. It does not differentiate Blender node evaluation automatically, and discrete placement, tool choice, clipping, and order are not made smooth by calling `grad`. Sources: [JAX API](https://docs.jax.dev/en/latest/jax.html) and [`jax.scipy.optimize.minimize`](https://docs.jax.dev/en/latest/_autosummary/jax.scipy.optimize.minimize.html).

For the next experiment, use a deterministic guided candidate generator and measurable comparison rather than a solver. Optimization becomes worth adding only after a fixed tool, target renderer, allowed rotations, region semantics, and acceptable overlap are known.

## Construction approaches

### Fixed physical impressions

Proposed data flow:

1. Read one alpha plate in a declared millimetre coordinate system and generate candidate centers from a regular grid or a guide-derived set of points.
2. Evaluate alpha at each candidate and use it as a coverage or eligibility signal. Expose the threshold/response as a control; do not silently reinterpret it as paint opacity.
3. Attach one immutable footprint mesh per tool identity. Use the tool’s allowed orientation set or a guide-derived angle; keep footprint scale at `1` unless calibration permits another range.
4. Apply region inclusion, exclusion, and local overrides before emitting placements. A region may change eligibility, angle, spacing, or tool identity, but the precedence must be visible and deterministic.
5. Emit two products: placement records/footprint geometry and a center-to-center contact sequence. Add raised travel only in a separate execution preview until the machine’s contact and travel states are specified.

This approach gives direct owner control over guide position, region shape, tool selection, orientation rule, spacing, and coverage response. It preserves edits as source geometry and controls. It does not guarantee whole-footprint clearance from an exclusion region merely because a center is outside it; the footprint must be tested against the region. A grid gives candidate spacing, not an optimal packing or a guarantee against rotated-footprint overlap. These are algorithm limits to test, not native Geometry Nodes guarantees.

### Continuous paths

Proposed data flow:

1. Let the owner draw or edit one or more guide curves.
2. Resample them at a declared step, sample tangents, and create a centerline path or a family of offsets.
3. Clip or terminate each path against a region using a stated rule: start-point gate, midpoint gate, crossing split, or full swept-footprint clearance. The last option is the meaningful one for a brush and requires explicit geometry checks.
4. Use alpha to choose which paths exist, their spacing, their allowed length, or a separate deposition parameter. Keep these interpretations switchable; one plate does not prescribe one mapping.
5. Preview the stroke sweep separately from the centerline, then optionally pass open lines to vpype for simplification and travel ordering.

This approach is more natural for a brush that remains in contact along a stroke and gives the owner a visible relationship between guide edits and line construction. It has harder edge cases: ambiguous guide influence, competing guides, path intersections, turn limits, path order, and a brush width that must be considered during clipping. Native curve nodes provide useful operations, but a robust offset/clip/clearance stage remains custom or must be validated from a CAM tool.

### Contours, offsets, and optimization

Thresholding or contour extraction can turn an alpha plate into regions, then fill those regions with parallel offsets, spirals, or a medial-axis-like construction. This is useful when the question is boundary following or interior coverage, but it introduces a threshold and offset policy before any physical calibration. Fabex documents several analogous CNC strategies, which makes it a reference for vocabulary; it does not validate them for paint.

Optimization should be a separate layer over either construction. It needs a forward renderer and a score such as target coverage error plus penalties for guide departure, overlap, forbidden-region violation, tool changes, and raised travel. Start with locked tool identity and a small bounded parameter set. Treat a solver result as a candidate that the owner can inspect and edit, not as a replacement for the recipe.

## Data and integration contract

The canonical editable artifact should be the Blender project plus a small machine-neutral manifest. SVG is a rendered/exported view. At minimum, preserve:

| Data | Minimum fields |
| --- | --- |
| Artwork | artifact id/hash, canvas size, units, origin, axis direction, plate order |
| Plate and color | plate id, alpha source/hash, palette entry, color model, layer order |
| Tool | stable tool id, footprint asset/hash, dimensions, allowed orientation set, scale policy |
| Construction | method, guide/region ids, controls, locks/ranges/preferences, deterministic seed only if one is actually used |
| Placement/path | id, plate, tool, x/y (and z if relevant), orientation, centerline or footprint reference, contact state |
| Execution | ordered contact/travel segments, pen-up or raised moves, feed/pressure/loading fields only when hardware defines them |
| Constraints | workspace bounds, clearance policy, overlap policy, collision rules, validation results |

SVG can represent open or closed paths with line, curve, arc, and close-path commands; fills, strokes, transforms, IDs, groups, and metadata are part of the format. The W3C specification defines paths as geometry that can be filled or stroked and permits descriptive metadata: [SVG paths](https://www.w3.org/TR/SVG11/paths.html) and [SVG document structure](https://www.w3.org/TR/SVG11/struct.html). That is sufficient for layered visual output and can carry a manifest fragment in `<metadata>` or IDs.

SVG does not define this project’s tool identity, contact versus raised travel, machine axes, deposition state, calibrated footprint semantics, solver locks, or recipe relationships. Those can be encoded as private metadata, but a viewer or a path utility is not required to preserve or enforce them. vpype explicitly says it only partially uses SVG metadata and does not maintain full SVG consistency. Therefore keep the manifest/`.blend` project as the editable source, and treat SVG as a declared snapshot with a hash back to its inputs.

Mixbox should remain a comparison renderer around the existing baseline. The official project provides `mixbox.lerp` and a Python distribution named `pymixbox`; it describes the library as pigment-based and lists a CC BY-NC 4.0 license for non-commercial use. Sources: [official Mixbox repository](https://github.com/scrtwpns/mixbox), [Python usage](https://github.com/scrtwpns/mixbox#python), and [license](https://github.com/scrtwpns/mixbox#license). Recompose the same ordered alpha plates under RGB and Mixbox, label the result as a color-model comparison, and keep the accepted RGB output. Mixbox does not infer geometry, tool coverage, motion, or physical calibration, and ordinary SVG compositing does not become Mixbox compositing merely because colors were computed with it.

## Agent authoring: direct `bpy` versus Blender MCP

Direct `bpy` through the existing Blender CLI is the recommended source of truth. It is local, scriptable, reviewable, and already matches the repository’s prototype workflow. Use it to generate or revise node graphs, save a scene, evaluate the dependency graph, and export. The local system Python cannot import `bpy`; that is expected for Blender-hosted code and means the adapter must run under the selected Blender binary.

The current public [MCP for Blender](https://github.com/ahujasid/mcp-for-blender) is a third-party add-on plus a separate MCP server. Its README says the add-on opens a socket server, the server can execute arbitrary Python in Blender, and the connection has no authentication or encryption by default. It also documents a safe mode and warns that arbitrary code execution is powerful and dangerous. Sources: [components and capabilities](https://github.com/ahujasid/mcp-for-blender#components), [connection security](https://github.com/ahujasid/mcp-for-blender#environment-variables), and [limitations](https://github.com/ahujasid/mcp-for-blender#limitations--security-considerations).

MCP can make interactive graph inspection and owner-facing revision easier once a specific server/add-on pair is installed and verified. It is not currently configured in this repository’s `project-sets.json`, no live Blender MCP connection was available in this session, and no Blender service was started for this report. Use MCP as a convenience layer that invokes the same versioned `bpy` adapter; do not make a live socket session the only way to reproduce a graph or export.

## Bounded experiments

All experiments use the same recovered image and alpha plates. They are learning artifacts, not machine runs.

### Experiment A — fixed footprint, guide, and region (recommended first)

- **Uncertainty:** Can the owner understand and control fixed-tool placement through guides, regions, orientation, and coverage response without rewriting the graph?
- **Owner edits:** One guide curve, one exclusion/override region, fixed tool identity, orientation mode, candidate spacing, and alpha response threshold.
- **Artifacts:** Saved `.blend`, guide/region objects, centerline preview, fixed footprint preview, separate travel preview, SVG snapshot, manifest, and a small validation table.
- **Evidence:** Moving the guide changes affected orientations/placements; moving the region changes only the intended area; footprint dimensions remain fixed; every placement has tool, plate, position, and orientation; footprint overlap/clearance violations are counted; output is deterministic across two exports.
- **Dependencies:** Pinned Blender prototype environment and existing alpha assets only. No Fabex, vpype, MCP, or new package required.
- **Does not prove:** Physical brush coverage, pressure, paint loading, arbitrary tool scaling, final machine motion, or an image-optimal solution.

### Experiment B — continuous guide-following and swept preview

- **Uncertainty:** Does a continuous path give more useful control than discrete placements for the same plate, and where do clipping and spacing become the real problem?
- **Owner edits:** One or two drawn guides, resampling step, guide influence radius, path termination rule, alpha-to-spacing or alpha-to-length mapping, and brush-width preview.
- **Artifacts:** Editable guide curves, open centerline SVG, swept coverage preview, region-clipping diagnostics, travel-order preview, and measurements for path length, number of segments, minimum separation, and out-of-region sweep.
- **Evidence:** Guide edits produce localized predictable path edits; the stated termination rule matches the output; minimum spacing and sweep clearance are measured; centerlines remain distinct from filled preview geometry.
- **Dependencies:** Native Blender curves/GN; vpype may be compared later but is not required.
- **Does not prove:** Calibrated deposition, optimal line ordering, or that a single guide semantics generalizes to all plates.

### Experiment C — same open paths through a postprocessor

- **Uncertainty:** How much raised travel and path complexity can a line-oriented postprocessor remove without losing the project’s layer and identity information?
- **Owner edits:** None in the construction graph; choose vpype operations and tolerances, then inspect before/after.
- **Artifacts:** Input centerline SVG, vpype output SVG, path statistics, layer comparison, pen-up travel visualization, and a manifest/hash comparison.
- **Evidence:** Report path count, total contact length, estimated raised travel, segment count, layer order, and whether IDs/metadata/tool identity survive. Treat any loss as a failed round-trip requirement, not as a cosmetic issue.
- **Dependencies:** An isolated pinned vpype environment; no production dependency decision.
- **Does not prove:** Image quality, footprint placement, machine compatibility, or paint behavior.

## Recommendation and sequence

Run Experiment A first. It most directly tests the owner’s requested CAM-like control model, reuses the already demonstrated Blender authoring path, and isolates physical-footprint semantics from continuous-path semantics. It also produces the data that Experiment B needs: guide objects, region precedence, units, tool identity, explicit orientation, and separate geometry views.

Suggested sequence after the research ticket:

1. Agree on one real tool footprint, its allowed orientations, the artwork coordinate system, and the meaning of alpha for the experiment.
2. Build only Experiment A and record deterministic geometry, placement metadata, coverage, overlap, and guide/region edit evidence.
3. Decide whether continuous strokes solve a real control problem; if yes, build Experiment B with a declared clipping and termination rule.
4. If centerlines are useful, run Experiment C as a separately pinned postprocessing comparison. Keep the original centerlines and manifest beside the processed SVG.
5. Specify the later interface around observed controls and validation results. Add optimization only after a forward coverage renderer, objective, fixed-tool constraints, and hardware execution fields are available.

## Unknowns that can change the recommendation

These are the only open facts that materially affect the order above:

- **Tool behavior:** Is the real tool a fixed footprint, a continuous brush, or both? Can it rotate, lift, change pressure, or vary paint loading? If fixed impressions cannot rotate, orientation controls become a guide constraint rather than a variable.
- **Machine contract:** What axes, workspace, units, contact height, travel state, speed, and file format exist? Without this, G-code or any machine-specific export would be premature.
- **Target meaning:** Does alpha mean coverage, opacity, paint amount, or a desired visual result? This changes both the forward renderer and the acceptance measurements.
- **Owner interaction:** Should a guide prescribe direction, initialize it, or merely bias a later solve? Should regions override, mask, or blend with global rules?
- **Canonical artifact:** Is the editable deliverable a `.blend` recipe plus manifest, a separate project format, or an SVG-centric workflow? SVG alone cannot carry the full semantics safely.
- **Distribution constraints:** Fabex’s GPL-3.0 and Mixbox’s CC BY-NC 4.0 terms matter if either is bundled into a distributed product; vpype’s MIT license is less restrictive but its semantic limits remain.

## Local availability checks

Read-only checks were run on 2026-09-20; no packages were installed and no Blender or MCP service was started.

```text
$ git status --short --branch
## build/0.1.0...origin/build/0.1.0

$ command -v blender && blender --version | head -n 3
/usr/bin/blender
Blender 4.0.2

$ python3 --version
Python 3.12.3

$ python3 - <<'PY'
import importlib.util
for name in ('bpy', 'vpype', 'mixbox', 'numpy', 'PIL'):
    print(f'{name}:', bool(importlib.util.find_spec(name)))
PY
bpy: False
vpype: False
mixbox: False
numpy: True
PIL: True

$ command -v vpype
# no output; command not found

$ find /home/reidsurmeier -maxdepth 5 -iname '*fabex*' -o -iname '*blender*cam*'
# no output

$ sed -n '1,80p' project-sets.json
{
  "gitnexus": true,
  "skills": [],
  "mcp": []
}
```

The repository’s checked prototype requirements pin NumPy 1.24.3, Pillow 12.2.0, and `pymixbox` 2.0.0, but those requirements are not proof of installation in the system interpreter. The local check above intentionally reports the system environment only.

## Primary sources consulted

- [Blender Geometry Nodes fields](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/fields.html), [Instance on Points](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/instances/instance_on_points.html), [Resample Curve](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/resample_curve.html), [Curve to Mesh](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/curve_to_mesh.html), [Trim Curve](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/curve/operations/trim_curve.html), and [Points to Curves](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/point/points_to_curves.html).
- [Blender GeometryNodeTree Python API](https://docs.blender.org/api/current/bpy.types.GeometryNodeTree.html) and [evaluated geometry Python example](https://github.com/blender/blender/blob/main/doc/python_api/examples/bpy.types.GeometrySet.0.py).
- [FabexCNC documentation](https://spectralvectors.github.io/blendercam/), [code overview](https://spectralvectors.github.io/blendercam/overview.html), [installation](https://spectralvectors.github.io/blendercam/install.html), and [repository](https://github.com/vilemduha/blendercam).
- [vpype repository](https://github.com/abey79/vpype), [cookbook](https://vpype.readthedocs.io/en/latest/cookbook.html), [release 1.15.0](https://github.com/abey79/vpype/releases/tag/1.15.0), and [limitations](https://github.com/abey79/vpype#what-vpype-isnt).
- [W3C SVG 1.1 paths](https://www.w3.org/TR/SVG11/paths.html) and [document structure/metadata](https://www.w3.org/TR/SVG11/struct.html).
- [JAX API](https://docs.jax.dev/en/latest/jax.html) and [`jax.scipy.optimize.minimize`](https://docs.jax.dev/en/latest/_autosummary/jax.scipy.optimize.minimize.html).
- [Official Mixbox repository](https://github.com/scrtwpns/mixbox), [Python usage](https://github.com/scrtwpns/mixbox#python), and [license](https://github.com/scrtwpns/mixbox#license).
- [MCP for Blender repository](https://github.com/ahujasid/mcp-for-blender), [components](https://github.com/ahujasid/mcp-for-blender#components), [connection security](https://github.com/ahujasid/mcp-for-blender#environment-variables), and [limitations](https://github.com/ahujasid/mcp-for-blender#limitations--security-considerations).
