"""Export an edited .blend without rebuilding its node graphs or tool shapes."""
import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from modules.blender_recipes.prototype import export_svg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--spacing", type=float)
parser.add_argument("--density", type=float)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
scene = bpy.context.scene
controls = bpy.data.objects.get("RECIPE CONTROLS · select to tune")
if controls is None or "painting_inks_json" not in scene:
    raise ValueError("Open a generated painting-recipes.blend before exporting")
for name, value, low, high in [("Spacing mm",args.spacing,1,30),("Density",args.density,0,8)]:
    if value is not None:
        if not low <= value <= high:
            raise ValueError(f"{name} must be in [{low},{high}]")
        controls[name] = value
controls.update_tag()
bpy.context.view_layer.update()
objects = [bpy.data.objects[name] for name in json.loads(scene["painting_objects_json"])]
args.output.parent.mkdir(parents=True,exist_ok=True)
counts = export_svg(objects,json.loads(scene["painting_inks_json"]),scene["painting_width_mm"],scene["painting_height_mm"],args.output)
print(json.dumps({"svg":str(args.output),"polygons":sum(counts),"graph_rebuilt":False}))
