# Pepsi: full-image JAX solve, one black plate, Blender contours

This is the corrected image-driven study for [issue 12](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/12). It uses the exact supplied `source.png` in the adjacent rejected draft; it does not redraw the Pepsi logo, ICE, CUCUMBER, or the ice by hand.

1. `single_black_solve.py` converts all 906×906 source pixels to grayscale and runs the preserved JAX alpha optimizer for 700 steps with one black ink on white paper. `black-alpha16.png`, `black-alpha-float32.npz`, `black-composite.png`, and `solve-receipt.json` are its outputs. The resulting composite RMSE against the grayscale target is **0.000935**. This is a faithful single-color tonal target, not a proposed deposited toolpath.
2. `alpha_contours.py` extracts a selected level from that plate. `--threshold` and `--blur-px` can change the contour input without editing source code. `source-contours.json` is the data passed to Blender.
3. Blender 4.3.2, reached through Blender MCP 2.0.0, built `jax-contour-study.blend`. The **JAX plate | contour controls** Geometry Nodes group exposes **Sample spacing mm** and **Smooth iterations**. `contour-study.svg` was exported from the evaluated node result, not from source curve coordinates. Raising spacing from 1 to 2 mm changed evaluated points from 5,327 to 2,680.
4. `evaluate_contours.py` rendered the actual exported SVG at hairline and nominal 3 mm width. The hairline preview shows image-derived typography and ice contours. The 3 mm preview shows collisions and loss of fine separation.

![JAX black plate](black-composite.png)
![Blender hairline contours](contour-hairline.png)
![Nominal 3 mm contour footprint](contour-3mm.png)

## Constraint result

`path-evaluation.json` reports **70 SVG paths**, where the required count is **one**. At a nominal 3 mm width, **5,098 raster pixels** are covered by at least two distinct contour paths. Those facts disqualify the SVG as a single continuous non-overlapping deposition path. All files use the 228.6×304.8 mm page; the square image occupies the center 228.6×228.6 mm. A connected lattice and machine travel have not been generated. Do not send this SVG to the extruder.

This study isolates the next toolpath problem: choose which black-plate features deserve the limited 3 mm footprint, then connect them into a noncrossing, non-retracing curve while preserving the supplied letterforms as far as that physical width allows. The current contours are useful reference geometry for that planner; they are not the planner itself.

## Reproduce

Use the existing JAX environment and Blender installation:

```bash
/home/reidsurmeier/plotter-separation-rebuild/.venv/bin/python modules/blender_recipes/single_black_solve.py
/home/reidsurmeier/plotter-separation-rebuild/.venv/bin/python modules/blender_recipes/alpha_contours.py --threshold .4 --blur-px .7
/home/reidsurmeier/.local/opt/blender-4.3.2/blender -b --factory-startup --python modules/blender_recipes/alpha_contours_blender.py
/home/reidsurmeier/plotter-separation-rebuild/.venv/bin/python modules/blender_recipes/evaluate_contours.py
```

The committed `.blend` was built through the live Blender MCP connection. The headless Blender command reproduces the same scene and exported geometry; it may create an ignored `.blend1` backup. The source scripts stay in their respective modules; the preserved legacy solver is called but not modified.
