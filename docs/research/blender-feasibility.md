# Blender feasibility for editable painting recipes

Research date: 2026-09-20. Resolves [Establish Blender capabilities for alpha-driven SVG marks](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/3). Documentation/source investigation only; no prototype, installation, server startup, or painting-machine operation.

Blender is a credible candidate for **agent-authored, editable recipes with several useful choices and controls per painting**. Native node groups support that interaction. Producing physically scaled SVG centerlines from the evaluated result is a separate problem requiring a small export comparison. Nothing here demonstrates better painting output or chooses Blender as the final workflow.

## What is actually available here

Read-only commands returned:

```text
command -v blender
/usr/bin/blender
blender --version
Blender 4.0.2
/home/reidsurmeier/.local/opt/blender-4.3.2/blender --version
Blender 4.3.2
build hash: 32f5fdce0a0a
```

These commands identify binaries, not working interactive sessions. No Blender tool appears in this session's callable tool metadata. Targeted searches found no Blender MCP entry in Codex/Claude configurations or the workflow MCP registry, no Blender MCP package under the local uv cache, and no MCP addon in the checked Blender 4.3 user/script directories. This establishes **no verified available integration**, not proof that none exists elsewhere or on another machine. No remote host is known. Consequently there is no locally identified MCP implementation whose installed source/version can honestly be audited.

## Capabilities and interfaces

| Concern | Verified capability | Consequence for this project |
| --- | --- | --- |
| Raster plate input | Geometry Nodes Image Texture samples an image using a Vector field and returns Color and Alpha. [Image Texture](https://docs.blender.org/manual/fi/4.3/modeling/geometry_nodes/texture/image.html) | A plate can drive mark decisions after explicitly mapping painting coordinates into image coordinates. Sampling is not automatic tracing or brush planning. |
| Editable recipe | A Geometry Nodes modifier references a node group; each modifier can carry its own input values even when groups are shared. [Modifier](https://docs.blender.org/manual/en/4.3/modeling/modifiers/generate/geometry_nodes.html) | Agent builds the graph; owner chooses a recipe and tunes exposed values for each painting/plate. |
| Multiple options | Node groups can be nested, reused and appended from another blend file. Their sockets have names, descriptions and defaults. [Node groups](https://docs.blender.org/manual/en/4.3/interface/controls/nodes/groups.html) Menu Switch exposes named choices in the modifier UI. [Menu Switch](https://docs.blender.org/manual/es/4.3/modeling/geometry_nodes/utilities/menu_switch.html) | Several reusable mark recipes or a menu of recipe branches can exist without requiring the owner to rewire graphs for each variation. Which options are useful remains a visual design question. |
| Planar mark representation | Curves can be resampled into poly splines using count, approximate spacing or evaluated points, with per-spline fields. [Resample Curve](https://docs.blender.org/manual/en/4.3/modeling/geometry_nodes/curve/operations/resample_curve.html) | Inference: generate curves in a common XY plane and expose angle, spacing, length and sampling controls. Alpha can influence these fields. Specific mark construction and treatment of gaps still need a prototype. |
| Grease Pencil bridge | The 4.3 Curves to Grease Pencil node accepts curves or curve instances and can map instances to layers; mixed realized geometry/instances need care. [Conversion node](https://docs.blender.org/manual/vi/4.3/modeling/geometry_nodes/curve/operations/curves_to_grease_pencil.html) | A native curve-to-Grease-Pencil route exists in the installed 4.3 generation. Layer organization does not itself preserve paint identity or physical order. |

A grayscale “alpha plate” may store coverage in RGB rather than its PNG alpha channel. Recovering the old interface must establish this before choosing a socket. It must also settle coverage range, image origin, dimensions, plate identity and order, and whether color management applies to stored coverage. Blender's ordinary color/alpha operations are not a replacement for the existing Mixbox paint model.

## SVG is the main feasibility seam

The installed 4.3.2 exporter reads **evaluated Grease Pencil objects**, including modifiers. It groups layers, projects coordinates to screen, reverses Y, and writes a pixel-sized SVG/viewBox. Depending on stroke settings it emits polylines/polygons or filled outline paths. It is therefore genuine evaluated-geometry export, but still a projected illustration export rather than a direct XY-to-millimetres contract. [Pinned SVG exporter source](https://github.com/blender/blender/blob/v4.3.2/source/blender/io/grease_pencil/intern/grease_pencil_io_export_svg.cc)

Its operator explicitly locates a 3D View area and cancels if none exists. A plain background invocation cannot be assumed to support this route. An interactive orthographic view may suffice for a comparison, but view, framing and scale must be fixed and checked. [Pinned operator source](https://github.com/blender/blender/blob/v4.3.2/source/blender/editors/io/io_grease_pencil.cc)

Two paths deserve comparison later:

1. Native curves → Grease Pencil → SVG, with controlled projection, uniform stroke settings and explicit normalization to painting units. Check that output contains the intended centerlines rather than brush outlines.
2. A small Python adapter that reads the evaluated planar curve/point representation and writes SVG in explicit physical coordinates. The exact evaluated-data extraction method and preservation of curve breaks/attributes must be verified on the chosen Blender version; this report does not assert an implemented exporter.

Do not infer headless export from the ability to execute Python remotely. Geometry evaluation, viewport presentation and SVG serialization are different interfaces.

## Version constraints

The two installed versions are not interchangeable for Grease Pencil. Blender 4.3 changed its architecture, and files saved using it do not load correctly in 4.2 or earlier. Keep legacy assets intact and pin the binary used for any later recipe. [4.3 compatibility notes](https://developer.blender.org/docs/release_notes/4.3/grease_pencil/)

Official later bug-fix notes list incorrect 4.3 SVG export resolution, procedural Grease Pencil export crashes and incorrect Bézier SVG output. These are specific reasons to test units and generated geometry before adopting the installed 4.3.2 native exporter. They do not prove that every candidate recipe will fail. [4.5 bug fixes](https://developer.blender.org/docs/release_notes/4.5/bugfixes/)

## MCP candidate, not installed capability

As a source-only candidate, ahujasid's project is currently named `mcp-for-blender` (formerly `blender-mcp`). It comprises an MCP server and a socket addon inside Blender; the README requires a running addon connection and states Blender 3.0 or newer. That broad minimum does not promise every Geometry Node exists. [Project README](https://github.com/ahujasid/mcp-for-blender/blob/6f992ffbca3cb715d111fc640b737b808632273c/README.md)

At inspected upstream commit `6f992ffbca3cb715d111fc640b737b808632273c`, `execute_blender_code` sends Python to the addon, and `describe_node_type` exposes actual node socket/property schemas. This could let an agent build and inspect native graphs. The optional safe mode restricts direct file operations while allowing Blender export operators; a custom writer must account for that execution policy. [MCP server source](https://github.com/ahujasid/mcp-for-blender/blob/6f992ffbca3cb715d111fc640b737b808632273c/src/blender_mcp/server.py) The addon executes the code with `bpy` in its namespace. [Addon source](https://github.com/ahujasid/mcp-for-blender/blob/6f992ffbca3cb715d111fc640b737b808632273c/addon.py)

No MCP connection, node construction, image loading or SVG export was tested. Choosing, pinning and verifying an integration is future prerequisite work, not a recovered fact.

## Minimal comparison and remaining owner decisions

1. Recover one legacy run with original plates, settings and SVG output. Establish what the plate values mean and the machine's expected SVG units/centerlines.
2. Agree on a small set of visibly distinct recipes worth exploring—for example directional hatching and short curved marks. These are examples, not selected styles. The agent authors editable groups and exposes useful controls; the owner explores them.
3. For the same plates and physical size, compare native export with the smallest evaluated-geometry adapter if native export fails the coordinate/centerline requirements. Check units, Y orientation, breaks, plate order and sampled shape against the source geometry.
4. Review images of exported SVGs and the actual tuning experience. Record whether owner-selected variations require only controls/recipe selection, and whether the chosen controls produce useful changes. Record path count, coverage, processing time and file size as supporting evidence.
5. Decide whether the result earns a fuller Blender workflow. Open questions are which mark families matter first, whether tuning is mainly per painting or per plate, and what downstream renderer/machine accepts as a stroke. Physical brush width and coverage calibration remain separate from an attractive SVG preview.

This report resolves feasibility research with explicit availability limits. It does not resolve recipe selection, recover the legacy pipeline, or constitute a Blender implementation spec.
