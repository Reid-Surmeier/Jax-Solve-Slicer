"""Export three issue-12 infill variants through Blender's evaluated curves."""

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpha_contours_blender import evaluated_paths
from two_plate_blender import OUT, make_curve, save_svg


def main(selected):
    contour_names = ("JAX blue plate | source contours",
                     "JAX green plate | source contours")
    for name in selected:
        plan = json.loads((OUT / f"green-infill-{name}-plan.json").read_text())
        if name == "parallel-final":
            bpy.ops.wm.open_mainfile(filepath=str(OUT / "two-plate-contours.blend"))
            infill = make_curve("JAX green plate | selective infill and wide frame ties",
                                [plan["frame_mm"]] + plan["paths_mm"])
            names = contour_names
        else:
            bpy.ops.wm.open_mainfile(filepath=str(OUT / "merged-material.blend"))
            infill = make_curve(f"JAX green plate | {name} infill and anchors", plan["paths_mm"])
            names = (*contour_names, "JAX merged material | frame and source-derived shading")
        bpy.context.view_layer.update()
        paths = []
        for object_name in (*names, infill.name):
            evaluated, _points = evaluated_paths(bpy.data.objects[object_name])
            paths.extend(evaluated)
        save_svg(f"green-infill-{name}.svg", paths)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"green-infill-{name}.blend"))
        print(f"GREEN_INFILL {name} {len(paths)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("parallel", "diagonal", "crosshatch", "parallel-final"))
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    selected = parser.parse_args(args).variant
    main((selected,) if selected else ("parallel", "diagonal", "crosshatch"))
