"""Export three issue-12 infill variants through Blender's evaluated curves."""

import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpha_contours_blender import evaluated_paths
from two_plate_blender import OUT, make_curve, save_svg


CONTOUR_NAMES = ("JAX blue plate | source contours",
                 "JAX green plate | source contours")


def clean_base():
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "two-plate-contours.blend"))
    source = ET.parse(OUT / "two-plate-contours.svg").getroot()
    removed = []
    for index, element in enumerate(source.findall(".//{http://www.w3.org/2000/svg}path")):
        points = [tuple(map(float, token.split(","))) for token in element.get("d").split()[1::2]]
        if sum(math.dist(a, b) for a, b in zip(points, points[1:])) < 6:
            removed.append(index)
    for source_index in reversed(removed):
        object_name = CONTOUR_NAMES[0 if source_index < 20 else 1]
        local_index = source_index if source_index < 20 else source_index - 20
        splines = bpy.data.objects[object_name].data.splines
        splines.remove(splines[local_index])
    for object_name in CONTOUR_NAMES:
        obj = bpy.data.objects[object_name]
        obj.modifiers[0]["Socket_2"] = 2
    scene_path = OUT / "green-infill-final-contours.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    paths = []
    for object_name in CONTOUR_NAMES:
        evaluated, _points = evaluated_paths(bpy.data.objects[object_name])
        paths.extend(evaluated)
    save_svg("green-infill-final-contours.svg", paths)
    print(f"GREEN_CLEAN_CONTOURS {len(paths)} removed {len(removed)}", flush=True)


def main(selected):
    for name in selected:
        plan = json.loads((OUT / f"green-infill-{name}-plan.json").read_text())
        if name == "parallel-final":
            bpy.ops.wm.open_mainfile(filepath=str(OUT / "green-infill-final-contours.blend"))
            infill = make_curve("JAX green plate | selective infill and wide frame ties",
                                [plan["frame_mm"]] + plan["paths_mm"])
            names = CONTOUR_NAMES
        else:
            bpy.ops.wm.open_mainfile(filepath=str(OUT / "merged-material.blend"))
            infill = make_curve(f"JAX green plate | {name} infill and anchors", plan["paths_mm"])
            names = (*CONTOUR_NAMES, "JAX merged material | frame and source-derived shading")
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
    parser.add_argument("--variant", choices=("parallel", "diagonal", "crosshatch", "parallel-final", "clean-base"))
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    selected = parser.parse_args(args).variant
    clean_base() if selected == "clean-base" else main((selected,) if selected else ("parallel", "diagonal", "crosshatch"))
