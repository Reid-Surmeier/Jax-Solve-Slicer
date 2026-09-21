"""Export three issue-12 infill variants through Blender's evaluated curves."""

import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpha_contours_blender import evaluated_paths
from two_plate_blender import OUT, make_curve, save_svg


def main():
    source = OUT / "merged-material.blend"
    names = ("JAX blue plate | source contours",
             "JAX green plate | source contours",
             "JAX merged material | frame and source-derived shading")
    for name in ("parallel", "diagonal", "crosshatch"):
        bpy.ops.wm.open_mainfile(filepath=str(source))
        plan = json.loads((OUT / f"green-infill-{name}-plan.json").read_text())
        infill = make_curve(f"JAX green plate | {name} infill and anchors", plan["paths_mm"])
        bpy.context.view_layer.update()
        paths = []
        for object_name in (*names, infill.name):
            evaluated, _points = evaluated_paths(bpy.data.objects[object_name])
            paths.extend(evaluated)
        save_svg(f"green-infill-{name}.svg", paths)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"green-infill-{name}.blend"))
        print(f"GREEN_INFILL {name} {len(paths)}", flush=True)


if __name__ == "__main__":
    main()
