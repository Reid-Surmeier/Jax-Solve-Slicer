# Single path Pepsi prototype

[Prototype issue](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/12). Source: the user supplied `source.png` (unaltered copy from `.orca/drops`). This is a separate, throwaway study of a nominal 3 mm continuous extrusion, not a machine-ready file.

Open `single-path.blend`. Select **EDIT PATH | one start, one end**, enter Edit Mode, and move curve points. The Geometry Nodes modifier turns that curve into a flat 3 mm footprint preview. Its `Tool width mm` input is exposed for comparison; the evaluated demo and validation use exactly 3 mm. The source image is packed in the file and hidden as a reference object. `single-path.svg` is a flat vector drawing in millimeters, exported from the saved Blender curve.

Re-export after editing and saving the `.blend`:

```bash
/home/reidsurmeier/.local/opt/blender-4.3.2/blender -b docs/prototypes/pepsi-single-pass/single-path.blend --python-exit-code 1 --python modules/blender_recipes/single_path_export.py
python3 modules/blender_recipes/single_path_validate.py
```

The export does not rebuild the path or node graph. The validator checks one open path, intersections, envelope, and exact centerline separation between segments more than 8 mm apart along the route. The 8 mm local run exclusion captures continuous bending of the deposited line; the check does not model real extrusion flow at corners.

To reconstruct the supplied prototype, run `python3 modules/blender_recipes/single_path_prototype.py` (requires Pillow), then run `single_path_blender.py` from Blender through MCP `execute_blender_code` or headless `--python`. Rebuilding overwrites the committed `.blend` and SVG, so copy edited variants first. `path.json` is the original construction receipt; later Blender edits live in the saved curve, not that receipt.

## Evidence

- `blender-receipt.json`: Blender 4.3.2, one open 295-point spline, 3,540 evaluated preview vertices, zero Z thickness, packed input image. The scene was built by the pinned Blender MCP 2.0.0 client connected to the 4.3.2 GUI add-on on localhost.
- `geometry-check.json`: zero centerline crossings; 4,212.52 mm route length; 3.543 mm exact minimum separation for nonlocal runs; deposited bounds 6.5–215.167 mm X and 38.5–276.167 mm Y.
- `preview.png`: the portable SVG-style preview. `blender-footprint.png`: a headless Workbench render of the saved evaluated Geometry Nodes mesh. Both were visually inspected.

The artwork keeps PEPSI, the globe, ICE, and CUCUMBER recognizable as simplified outlines. A connected left spine and word feet make every feature part of one path. Letter counters and the globe wave are opened to avoid isolated loops. The result deliberately omits gradients and the original colors. Physical adhesion, real 3 mm line width, corner buildup, and machine execution are unverified.
