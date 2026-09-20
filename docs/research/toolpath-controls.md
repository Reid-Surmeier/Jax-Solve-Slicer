# Controlling painting paths in Blender

Research for [Map editable toolpath controls before designing the painting slicer](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/10), 2026-09-20.

## What to learn first

The next prototype should teach **how an edit changes path construction**. The existing three footprint examples are technical evidence that Blender can consume plates and export evaluated geometry. They do not establish the editor the owner wants.

| Control area | Example of an edit |
| --- | --- |
| Physical tool | Choose an actual fixed instrument and its allowed rotation. |
| Region | Protect an eye; apply different settings to a cheek or background. |
| Guide | Move a curve to change the local direction of the line work. |
| Construction rule | Change spacing, stopping conditions, overlap or influence of the alpha plate. |
| Execution | Lock stroke direction and paint order; inspect contact and raised travel. |

A useful small experiment would keep one recovered alpha plate, one fixed physical footprint, one editable region and one editable guide. The agent builds the construction; the owner moves the guide and changes two scoped variables. Compare the regenerated centerlines and footprint coverage. Travel preview is a separate view, with no claim of machine-ready motion. The exact construction algorithm remains a discussion topic; this report does not approve an editor implementation.

## Re-evaluation, solving and export

Moving source curves or changing node inputs re-evaluates dependent geometry. Interactive speed has not been benchmarked for a useful painting workload. Changing a guide need not re-solve the color plates; changing the pigment model or palette may require a new color solve. Asking the system to search for placements/angles that best match an image requires an explicit optimization objective and compatible renderer.

Save guides, regions, node graphs and control values in the Blender project. Exported SVG is an output snapshot. Our tested exporter writes evaluated filled polygons in millimeters; it does not retain guide relationships, tool contact state or a motion schedule. General SVG import/export round-trip fidelity has **not** been established. Re-importing a flattened SVG should not be presented as recovering an editable recipe. An adapter for centerlines and explicit tool orientation needs a separately specified data contract when that experiment is selected.

Mixbox belongs in the predicted color/coverage comparison. The working diagnostic recomposes existing RGB-solved plates with official pymixbox; it does not optimize their placement or convert SVG viewers into pigment renderers. Preserve the original RGB result alongside it until the intended color model and physical calibration are decided.

## Geometry Nodes capability investigation


Research checked 2026-09-20 against official Blender documentation and the current local `modules/blender_recipes/prototype.py`. No implementation or execution was performed for this investigation.

The useful model is **editable source geometry + rules that vary across the painting + construction constraints → regenerated centerlines and a separate footprint preview**. This is a candidate interface for discussion, not a selected implementation. Adaptability means changing inputs, relationships and constraints; repeatable generation remains useful and does not imply random placement.

## Vocabulary and native capability

A **field** is a calculation evaluated at each geometry element. It can supply a different angle, length, selection or offset at each point. The same calculation may produce different results when evaluated after geometry moves; original values must be captured if later steps should retain them. Native fields therefore support spatially varying behavior rather than only global sliders. [Blender 4.3 Fields](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/fields.html)

| Owner-facing control | Concrete meaning | Native ingredients and limits |
| --- | --- | --- |
| **Starting geometry / guides** | Move a starting line, draw a curve, or edit control points; generated work follows that edit. | Blender provides freehand curve drawing with fitting tolerance and editable curves. Object Info reads external geometry/transforms into a graph. Choose a shared painting plane and transform convention. [Draw](https://docs.blender.org/manual/fi/4.3/modeling/curves/tools/draw.html), [Object Info](https://docs.blender.org/manual/it/4.3/modeling/geometry_nodes/input/scene/object_info.html) |
| **Position and direction** | Where lines begin; which direction they point or follow at each location. | Set Position modifies selected geometry points, or only instance origins if given instances. Curve tangents and Sample Curve supply direction along guides. A tangent along one guide is not automatically a direction field over the entire painting; spreading/interpolating that guidance needs a defined rule. [Set Position](https://docs.blender.org/manual/en/4.4/modeling/geometry_nodes/geometry/write/set_position.html), [Sample Curve](https://docs.blender.org/manual/en/3.6/modeling/geometry_nodes/curve/sample/sample_curve.html) |
| **Distance between paths** | Keep adjacent passes a chosen distance apart, perhaps closer in dark areas. | This is a construction constraint. A grid controls candidate point spacing; Poisson point distribution controls minimum separation of points. Neither guarantees clearance between full curved strokes. A path offset/fill or path-avoidance algorithm needs separate verification. [Point distribution](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/point/distribute_points_on_faces.html) |
| **Sampling along a path** | How finely a curve is represented or where operations happen along it. | Resample Curve controls count or approximate along-curve distance. It creates poly splines; count and length modes do not guarantee a maximum geometric approximation error. This is distinct from the distance between neighboring paths. [Resample Curve](https://docs.blender.org/manual/en/4.3/modeling/geometry_nodes/curve/operations/resample_curve.html) |
| **Amount of line work** | More or fewer starts, more total length, or more surface coverage. These are different quantities. | Point density is points per area, capped by minimum point distance in Poisson mode. A coverage map can modulate it, but density is not physical paint coverage. Physical length/area and brush width must be measured separately. [Point distribution](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/point/distribute_points_on_faces.html) |
| **Length and termination** | Set how far a line travels; stop at a region edge, a length limit, or another path. | Trim Curve changes spline start/end by length or fraction. In 4.3 it does not support cyclic splines. It does not compute intersections with arbitrary masks or split all crossings automatically. [Trim Curve](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/curve/operations/trim_curve.html) |
| **Width / overlap** | Preview the brush sweep and choose how much adjacent passes overlap. | Set Curve Radius varies a radius per control point; Curve to Mesh sweeps a profile using it. With no profile, Curve to Mesh outputs edge chains. Geometric radius is not calibrated brush contact width, pressure or paint deposition. [Radius](https://docs.blender.org/manual/sr/4.3/modeling/geometry_nodes/curve/write/set_curve_radius.html), [Curve to Mesh](https://docs.blender.org/manual/sl/4.3/modeling/geometry_nodes/curve/operations/curve_to_mesh.html) |
| **Regions and local overrides** | Make lines shorter near a detail, preserve a gap, or apply stronger guidance inside a selected area. | Selections/fields gate operations. Geometry Proximity provides nearest distance to mesh points/edges/faces and supports grouping; combine it with a distance-to-influence rule. Proximity is unsigned and does not establish inside/outside of a closed region. Whole-path clipping and brush clearance require additional construction logic. [Geometry Proximity](https://docs.blender.org/manual/es/4.3/modeling/geometry_nodes/geometry/sample/geometry_proximity.html) |
| **Image influence** | Decide whether a plate affects presence, spacing, length, width or another variable, and how strongly. | Image Texture samples Color/Alpha at supplied coordinates, with interpolation and outside-image modes. Image sampling does not itself identify contours, object meaning or a direction field. Gradients/guidance can be derived through an explicitly chosen calculation or supplied as another image. [Image Texture](https://docs.blender.org/manual/fi/4.3/modeling/geometry_nodes/texture/image.html) |

A scalar plate can guide several different constructions; it does not prescribe a unique line drawing. For example, fading a plate can reduce line count, shorten strokes, increase their spacing, or change a calibrated paint parameter. These produce different results even if the same numeric plate drives them. That mapping is a meaningful control the owner should be able to inspect and change.

## Scenarios that clarify the interface

These are feasible compositions to investigate, not implemented features or style selections.

1. **“Bend the direction of this area by moving this guide.”** Keep a drawn Bézier guide editable. Sample its tangent and define how nearby locations inherit direction, then regenerate paths. The missing rule is how guidance propagates across the area, how competing guides blend and what happens where directions become ambiguous. No randomness is needed. Native Object Info/Sample Curve provide source data; a direction field plus tracing/offset method completes the behavior.
2. **“Keep the brush out of this shape, with 2 mm clearance.”** Use editable exclusion geometry and evaluate distance against the whole intended brush sweep. Selecting start points alone can leave long strokes crossing the excluded area. Centerline clipping must account for brush width and preserve resulting disconnected path segments. Geometry Proximity provides distance measurements, not a finished CAM clearance solver.
3. **“Use closer passes in dark areas, but keep the same flow.”** Separate the guidance field from the coverage-to-spacing relationship. A response curve/range remapping can expose that relationship. Curving or converging paths require an actual spacing strategy; increasing point density alone does not hold inter-path spacing constant. A user should see which quantity is being controlled.
4. **“Change the guide, then shorten only the lines around this detail.”** A local mask supplies a per-curve length field while the guide remains a shared input. Decide whether the mask is evaluated at a line's start, midpoint or anywhere it crosses; these semantics materially change results. Save source curves and graph parameters so another edit reevaluates the construction instead of requiring a script rewrite.

For traced paths, Repeat Zones can carry geometry/data through iterations and Points to Curves can assemble grouped points in a supplied order. These are implementation ingredients for a field-following experiment, **not evidence of a ready-made robust path solver**. Step length, turn limits, stopping rules, curve-group identity and ordering all need explicit definitions. [Repeat Zone](https://docs.blender.org/manual/it/4.3/modeling/geometry_nodes/utilities/repeat_zone.html), [Points to Curves](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/point/points_to_curves.html)

## Instances, centerlines and editability

Instances reference repeated geometry and have per-point rotation/scale. Editing one source object can update its copies. A repeated curve may still be a centerline; a repeated filled polygon is a footprint. Realizing either does not convert a footprint into its brush trajectory. Separately connecting scattered points requires chosen curve groups and order; Points to Curves is not an optimized motion planner. [Instance on Points](https://docs.blender.org/manual/it/4.3/modeling/geometry_nodes/instances/instance_on_points.html), [Points to Curves](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/point/points_to_curves.html)

A Geometry Nodes modifier is already an editable procedural layer. Node-group inputs can differ between objects using the same group, so local/per-plate settings need not duplicate the construction. External guide objects can remain editable inputs. Realizing instances inside the graph does not by itself destroy procedural editability; applying the modifier or editing only a baked output is a different workflow. [Geometry Nodes modifier](https://docs.blender.org/manual/en/4.3/modeling/modifiers/generate/geometry_nodes.html), [Object Info](https://docs.blender.org/manual/it/4.3/modeling/geometry_nodes/input/scene/object_info.html)

The agent can author the node relationships and expose numerical, image and object inputs. The owner can tune rules or edit guides/regions using native Blender tools. A single all-purpose style selector does not express these relationships. Native capability also does not prove acceptable reevaluation speed: line count, samples per line, iterative checks and image resolution determine the workload.

## What the current prototype actually proves

Source review of `modules/blender_recipes/prototype.py`, functions `make_group` and `export_svg`, shows a grid → sampled plate → random acceptance → footprint instance → realized mesh → filled SVG polygon pipeline. Its three choices replace source footprint geometry; they do not provide alternate rules for constructing continuous toolpaths.

Its `Density` is a multiplier on the plate value before comparison with a random value; it is not measured area coverage. `Spacing mm` affects grid vertex count, so actual spacing also depends on integer rounding and Grid's endpoint layout. `Length mm` and `Width mm` scale footprint axes. `Rotation degrees` plus `Jitter degrees` sets instance orientation. The same random field participates in placement and angular variation. Output SVGs are closed filled footprints, not demonstrated brush centerlines. This is source evidence about the technical proof, not a request to fix or expand it.

## Version and scope

Most evidence is pinned to the installed Blender **4.3** generation. The 3.6 Sample Curve and 4.4 Set Position pages describe longstanding primitives; exact socket details should be confirmed against 4.3.2 before implementation. Current official Fields documentation retains the same per-element evaluation model, and current Points to Curves retains explicit grouping/ordering. Neither observation establishes that a Blender upgrade is needed for the control vocabulary above. [Current Fields](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/fields.html), [Current Points to Curves](https://docs.blender.org/manual/es/latest/modeling/geometry_nodes/point/points_to_curves.html)

Unresolved: which construction relationships matter most to the owner; how plate coverage should influence them; centerline versus filled-area downstream expectations; inter-path spacing/clearance algorithms; turn and length limits; calibration between geometry and paint. These should shape the next discussion before more editor or recipe development.

## Direct editing, rules and optimization are separate choices

| Interaction | Who chooses the geometry? | Example and requirement |
| --- | --- | --- |
| **Direct editing** | Owner or agent moves/draws actual guides or paths. | “Move this curve around the eye.” Native curve editing supplies the control; dependent graph results can regenerate. |
| **Procedural construction** | An explicit rule generates geometry from controls. | “Start paths every 2 mm and follow this guidance field until the mask ends.” Native fields and geometry operations can express parts or all of a chosen algorithm. The rule need not be random and does not automatically optimize resemblance. |
| **Optimization against a target** | A solver searches permitted parameter changes to reduce a defined error. | “Keep this instrument's shape fixed; choose positions and rotations whose combined footprints best reproduce this plate.” Requires a forward model of marks/overlap, an objective, allowed variables, constraints and a search/update method. |

The same visible controls could be **values**, **initial guesses**, **locked values**, **permitted ranges**, or **soft preferences** for an optimizer. For instance, a guide might set every local angle exactly, initialize angles before solving, or merely penalize departure from that direction. These meanings must be chosen explicitly; a slider alone does not reveal them. If physical instruments have fixed footprints, arbitrary width/length scaling may be invalid and should not be assumed as a solver freedom.

The documented Geometry Nodes field/repeat mechanisms perform user-defined calculations and iterations. The reviewed sources provide no built-in general image-target optimization facility or automatic gradient computation through an arbitrary node graph. A custom iterative solver could be authored with nodes, but its loss, update rule, convergence and constraints would still be new algorithm work. A loop alone is not an optimizer. [Fields](https://docs.blender.org/manual/id/4.3/modeling/geometry_nodes/fields.html), [Repeat Zone](https://docs.blender.org/manual/en/4.3/modeling/geometry_nodes/utilities/repeat_zone.html)

JAX explicitly provides `grad`/`value_and_grad`, and its `minimize` API accepts a differentiable scalar objective and initial parameters. This makes existing JAX machinery a plausible place to investigate continuous placement/orientation optimization, while Blender could host editable guides, constraints and previews. This is an architectural candidate, not evidence that the old alpha solver already optimizes toolpaths. JAX does not automatically differentiate Blender operations; a compatible forward model would be needed. Discrete instrument selection, line count, clipping and ordering also need suitable handling rather than assuming smooth gradients cover them. [JAX differentiation API](https://docs.jax.dev/en/latest/jax.html), [JAX minimize](https://docs.jax.dev/en/latest/_autosummary/jax.scipy.optimize.minimize.html)

A useful next explanation should show these three meanings with one target image and one physical mark model before asking the owner to choose controls. It should establish whether the aim is to direct a construction, let a solver choose a construction under guidance, or combine direct edits with both.

## CAM and slicer workflow investigation

2026-09-20. Primary documentation review; no installation or implementation. The requirement is owner-editable construction rules and local control. Deterministic regeneration is compatible with that requirement: the same edited project should reproduce the same paths.

## Useful precedents

Bambu Studio explicitly provides Global/Object/Part slicing parameters, project workflows, multiple plates, and a G-code viewer. The useful precedent is a saved project with scoped settings and inspectable generated output, rather than a choice among rendered styles. Its “painting tools” assign printing material and should not be confused with physical brush-path design. Source: [official repository feature list](https://github.com/bambulab/BambuStudio#what-are-bambu-studios-main-features).

PrusaSlicer modifier meshes apply settings to the intersection of a modifier and the model; modifiers can be positioned geometrically and carry local infill, speed and other overrides. For a painting editor, the corresponding design inference is a mask or drawn region that overrides a default recipe only where it applies. The hierarchy and overlap priority must be visible. Source: [official Modifiers documentation](https://help.prusa3d.com/article/modifiers_1767).

Fabex separates operation setup, operation area and movement. Documented controls include path angle, spacing between paths, sampling along paths, direction, and travel clearance. Its architecture distinguishes generated paths, simulation, operation chains and machine-specific postprocessors. Those distinctions transfer well; milling-specific quantities do not automatically transfer to paint. Sources: [official interface](https://spectralvectors.github.io/blendercam/interface.html), [official architecture](https://spectralvectors.github.io/blendercam/overview.html). This is a workflow reference, not a recommendation to install the whole CAM package.

vpype supplies optional downstream line sorting, merging, simplification and travel display. Sorting and merging can reverse paths by default; `--no-flip` preserves direction. Its path-order optimization runs within layers. `show --show-pen-up` distinguishes travel visually. SVG travel display is preview evidence, not production geometry. These are useful small planner operations, not an interactive painting editor or brush simulator. Source: [official CLI reference](https://vpype.readthedocs.io/en/latest/reference.html#linesort).

## Proposed five control layers

This table is a design inference from those precedents, not an existing feature claim.

| Control layer | Owner edits | Stored meaning / visible consequence |
| --- | --- | --- |
| Process and tool | Actual tool footprint, supported rotation, calibrated width/deposition, working units, speed range, paper, paint | A reusable tool/process preset; changing it changes feasible paths and their estimated coverage. |
| Plate and region | Paint order; editable masks; region priority; inherited settings | Each region says which alpha target and overrides it uses. Selected region highlights in the image and path views. |
| Guides | Draw/move a curve, choose flow direction, select protected contours, pin start/end intent | Guides constrain construction. They remain editable independently of generated marks. |
| Generator rules | Spacing, length bounds, overlap, curvature limit, guide influence, density response, edge treatment | An inspectable recipe regenerates only the affected construction. A hatch/curve/stamp may be one rule, never the whole editing model. |
| Execution and review | Freeze stroke direction where needed; reorder allowed groups; lift/travel policy; reload/clean/wait points | Separate coverage view and chronological motion view. Show contact paths, travel, tool orientation and schedule; export only after intended order is clear. |

Parameter scope should read as inherited default plus explicit overrides. Editing a region must not silently change other plates. If a manual path correction is allowed, save it as an explicit pinned edit or override; don't lose it when upstream rules regenerate.

## Geometry Nodes versus planner

Use Blender as the candidate editor for guides, masks and parameter groups, with Geometry Nodes generating visible curves and tool-footprint geometry. Treat that as the geometric stage: where the strokes lie and how their shape responds to edited inputs. Parent's separate Blender capability research should establish the exact supported nodes and export mechanics; this investigation did not verify those APIs because official manual fetches failed.

Keep chronological scheduling, machine limits and output translation in a planner/export adapter. Those may initially be existing small functions or a constrained vpype step; they need not become a new app or framework. The planner must respect locked plate order, directional strokes and grouping before trying to shorten travel. A geometry preview alone cannot establish acceleration feasibility, wet-paint interaction, or paint replenishment. Fabex's documented separation of operations, simulation and postprocessors supports this allocation; the precise implementation remains a prototype decision.

A path can have an XY tangent and a different tool orientation. A flat brush may turn its long axis while moving along a curve; a round pen's direction may be mechanically irrelevant but still affect deposition. An SVG filled polygon records an intended footprint, not a unique realizable tool trajectory or rotation schedule. Keep centerline, orientation and contact state available instead of treating every rendered outline as a machine instruction.

## Three editing scenarios to test

1. **Shape a cheek without changing the rest of the portrait.** Owner draws a curved guide over the cheek and masks that region. Increasing guide influence bends local path flow; shortening maximum length near the eyelid retains detail. The project keeps the original alpha target and shows under/overcoverage as the owner edits. Test that moving the guide updates local paths without re-solving colors or rewriting Python.

2. **Switch the background to a larger flat brush.** Owner assigns a broader calibrated tool to the background region, increases spacing proportionally, sets overlap and limits allowable tool rotation near the subject. The tool-footprint preview reveals gaps or incursions across the mask. This tests real construction variables, not switching to a named visual preset. The narrower tool and detail paths remain unchanged.

3. **Preserve a downward stroke while reducing wasted travel.** Owner locks stroke direction in a wet region, orders paint passes, and places a reload or wait event. The planner may reorder compatible strokes but may not flip them or reorder locked paint groups. A time scrubber shows paint contact, raised travel and orientation. Compare coverage and motion views so a shorter route cannot silently change the artistic result.

## Limits and next prototype question

Slicer infill extrudes a bead; milling removes material with a cutter; this machine deposits paint with a potentially deformable and asymmetric tool. Pressure, load, angle, speed, substrate and wetness need empirical calibration. A generic “width” parameter must not promise independently controllable width if the mechanism cannot produce it.

The next useful prototype question is: can the owner edit a region and guide, change two scoped construction variables, regenerate, and inspect both coverage and travel without editing source code? Build only enough to answer that question. No full slicer rebuild, new CAM installation, randomized output or production controller is implied by this research.
