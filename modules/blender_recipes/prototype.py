"""Throwaway native Geometry Nodes recipes; export their evaluated filled geometry."""
import argparse
import json
import math
from pathlib import Path
import sys
from xml.sax.saxutils import escape

import bpy
import numpy as np


def image_from_plate(name, plate):
    height, width = plate.shape
    image = bpy.data.images.new(name, width, height, alpha=True)
    image.colorspace_settings.name = "Non-Color"
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = plate[::-1, :, None]
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    return image


def footprint(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.hide_render = True
    obj.hide_set(True)
    return obj


def make_group(tools):
    group = bpy.data.node_groups.new("Painting · editable recipe", "GeometryNodeTree")
    group.is_modifier = True
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    specs = {
        "Plate": ("NodeSocketImage", None, None, None),
        "Canvas width mm": ("NodeSocketFloat", 180.0, 1, 3000),
        "Canvas height mm": ("NodeSocketFloat", 224.0, 1, 3000),
        "Spacing mm": ("NodeSocketFloat", 3.0, 1, 30),
        "Length mm": ("NodeSocketFloat", 5.0, .1, 30),
        "Width mm": ("NodeSocketFloat", 1.1, .1, 30),
        "Density": ("NodeSocketFloat", 2.6, 0, 8),
        "Rotation degrees": ("NodeSocketFloat", 0.0, -180, 180),
        "Jitter degrees": ("NodeSocketFloat", 16.0, 0, 90),
        "Recipe 0 hatch 1 curve 2 stamp": ("NodeSocketInt", 0, 0, 2),
        "Seed": ("NodeSocketInt", 0, 0, 10000),
    }
    sockets = {}
    for name, (kind, value, low, high) in specs.items():
        socket = group.interface.new_socket(name=name, in_out="INPUT", socket_type=kind)
        if value is not None:
            socket.default_value, socket.min_value, socket.max_value = value, low, high
        sockets[name] = socket.identifier
    nodes, links = group.nodes, group.links

    def node(kind, label, x, y):
        n = nodes.new(kind)
        n.label = n.name = label
        n.location = (x, y)
        n.width = 180
        return n

    inputs = node("NodeGroupInput", "Recipe controls", -1200, 200)

    def wire(value, socket):
        if isinstance(value, str):
            value = inputs.outputs[value]
        if isinstance(value, (float, int)):
            socket.default_value = value
        else:
            links.new(value, socket)

    def math_node(operation, a, b, label, x, y):
        n = node("ShaderNodeMath", label, x, y)
        n.operation = operation
        wire(a, n.inputs[0])
        wire(b, n.inputs[1])
        return n.outputs[0]

    grid = node("GeometryNodeMeshGrid", "Painting grid", -600, 600)
    for axis, dimension in [("X", "Canvas width mm"), ("Y", "Canvas height mm")]:
        wire(dimension, grid.inputs["Size " + axis])
        count = math_node("DIVIDE", dimension, "Spacing mm", axis + " spacing", -950, 600 if axis == "X" else 420)
        wire(count, grid.inputs["Vertices " + axis])
    position = node("GeometryNodeInputPosition", "Painting coordinates", -1200, -350)
    separate = node("ShaderNodeSeparateXYZ", "XY", -980, -350)
    links.new(position.outputs[0], separate.inputs[0])
    uv = node("ShaderNodeCombineXYZ", "Image UV", -350, -350)
    for axis, dimension in [("X", "Canvas width mm"), ("Y", "Canvas height mm")]:
        normalized = math_node("DIVIDE", separate.outputs[axis], dimension, axis + " normalized", -780, -350 if axis == "X" else -550)
        shifted = math_node("ADD", normalized, .5, axis + " image coordinate", -560, -350 if axis == "X" else -550)
        wire(shifted, uv.inputs[axis])
    texture = node("GeometryNodeImageTexture", "Sample alpha plate · non-color", -100, -300)
    texture.extension = "EXTEND"
    wire("Plate", texture.inputs["Image"])
    links.new(uv.outputs[0], texture.inputs["Vector"])
    probability = math_node("MULTIPLY", texture.outputs["Color"], "Density", "Coverage × density", 120, -300)
    random = node("FunctionNodeRandomValue", "Repeatable placement", -350, 200)
    random.data_type = "FLOAT"
    wire("Seed", random.inputs["Seed"])
    remove = math_node("GREATER_THAN", random.outputs[1], probability, "Skip uncovered samples", 350, 200)
    delete = node("GeometryNodeDeleteGeometry", "Coverage selects points", 560, 600)
    delete.domain = "POINT"
    links.new(grid.outputs[0], delete.inputs["Geometry"])
    links.new(remove, delete.inputs["Selection"])
    objects = []
    for index, tool in enumerate(tools):
        info = node("GeometryNodeObjectInfo", tool.name, -300, 1000 + index * 230)
        info.inputs["Object"].default_value = tool
        info.transform_space = "ORIGINAL"
        objects.append(info.outputs["Geometry"])
    chosen = objects[0]
    for index in [1, 2]:
        condition = math_node("GREATER_THAN", "Recipe 0 hatch 1 curve 2 stamp", index - .5, f"Recipe ≥ {index}", 0, 1000 + index * 230)
        switch = node("GeometryNodeSwitch", f"Tool choice {index}", 240, 1000 + index * 230)
        switch.input_type = "GEOMETRY"
        wire(condition, switch.inputs["Switch"])
        wire(chosen, switch.inputs["False"])
        wire(objects[index], switch.inputs["True"])
        chosen = switch.outputs[0]
    rotation = node("ShaderNodeCombineXYZ", "Tool rotation", 580, -100)
    centered = math_node("SUBTRACT", random.outputs[1], .5, "Centered variation", -100, 0)
    jitter = math_node("MULTIPLY", centered, "Jitter degrees", "Angular variation", 120, 0)
    degrees = math_node("ADD", "Rotation degrees", jitter, "Angle plus variation", 330, -100)
    radians = math_node("MULTIPLY", degrees, math.pi / 180, "Degrees to radians", 330, -300)
    wire(radians, rotation.inputs["Z"])
    scale = node("ShaderNodeCombineXYZ", "Physical tool footprint · mm", 580, -500)
    wire("Length mm", scale.inputs["X"])
    wire("Width mm", scale.inputs["Y"])
    scale.inputs["Z"].default_value = 1
    instances = node("GeometryNodeInstanceOnPoints", "Place selected tool", 800, 600)
    links.new(delete.outputs[0], instances.inputs["Points"])
    wire(chosen, instances.inputs["Instance"])
    wire(rotation.outputs[0], instances.inputs["Rotation"])
    wire(scale.outputs[0], instances.inputs["Scale"])
    realize = node("GeometryNodeRealizeInstances", "Real geometry for SVG export", 1040, 600)
    links.new(instances.outputs[0], realize.inputs[0])
    output = node("NodeGroupOutput", "Evaluated painting marks", 1270, 600)
    links.new(realize.outputs[0], output.inputs[0])
    return group, sockets


def export_svg(objects, inks, width, height, path):
    """Serialize evaluated polygon footprints, independent of viewport/camera."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
    counts = []
    for obj, ink in zip(objects, inks):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        color = "#" + "".join(f"{v:02x}" for v in ink["rgb"])
        lines.append(f'<g id="{escape(ink["id"])}" fill="{color}" fill-opacity="0.55">')
        for polygon in mesh.polygons:
            coords = [mesh.vertices[index].co for index in polygon.vertices]
            assert all(math.isfinite(float(v)) for coord in coords for v in coord)
            points = [(v.x + width / 2, height / 2 - v.y) for v in coords]
            d = "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in points) + " Z"
            lines.append(f'<path d="{d}"/>')
        counts.append(len(mesh.polygons))
        lines.append("</g>")
        evaluated.to_mesh_clear()
    lines.append("</svg>")
    path.write_text("\n".join(lines))
    assert sum(counts) > 0, "Empty evaluated Geometry Nodes output"
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alpha", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--width-mm", type=float, default=180)
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace an existing generated .blend")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if not 1 <= args.width_mm <= 3000:
        parser.error("width must be between 1 and 3000 mm")
    if (args.out / "painting-recipes.blend").exists() and not args.overwrite:
        raise FileExistsError("Preserving existing .blend edits: choose a new output directory or explicitly pass --overwrite")
    with np.load(args.alpha / "alpha_stack_float32.npz", allow_pickle=False) as archive:
        plates = archive["alpha_stack"]
    inks = json.loads((args.alpha / "metadata.json").read_text())["inkset"]["inks"]
    if plates.ndim != 3 or len(plates) != len(inks) or not plates.size:
        raise ValueError("Expected a nonempty plate,height,width stack matching the inks")
    if not np.isfinite(plates).all() or plates.min() < 0 or plates.max() > 1:
        raise ValueError("Alpha values must be finite and between zero and one")
    args.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = .001
    bpy.context.scene.unit_settings.length_unit = "MILLIMETERS"
    width, height = args.width_mm, args.width_mm * plates.shape[1] / plates.shape[2]
    tools = [footprint("Tool · short hatch", [(-.5,-.5,0),(.5,-.5,0),(.5,.5,0),(-.5,.5,0)], [(0,1,2,3)])]
    curve = []
    for i in range(13):
        t = i / 12
        curve.extend([(t-.5, math.sin(t*math.pi)*.5-.15,0),(t-.5, math.sin(t*math.pi)*.5+.15,0)])
    tools.append(footprint("Tool · curved band", curve, [tuple(range(0,26,2)) + tuple(range(25,0,-2))]))
    outer = [(0,-.5,0),(.5,0,0),(0,.5,0),(-.5,0,0)]
    inner = [(x*.5,y*.5,z) for x,y,z in outer]
    tools.append(footprint("Tool · diamond impression", outer+inner, [(i,(i+1)%4,(i+1)%4+4,i+4) for i in range(4)]))
    group, sockets = make_group(tools)
    controls = bpy.data.objects.new("RECIPE CONTROLS · select to tune", None)
    bpy.context.scene.collection.objects.link(controls)
    values = {"Spacing mm":3.0,"Length mm":5.0,"Width mm":1.1,"Density":2.6,"Jitter degrees":16.0,"Recipe 0 hatch 1 curve 2 stamp":0}
    for name,value in values.items():
        controls[name] = value
        source = next(s for s in group.interface.items_tree if s.name == name)
        controls.id_properties_ui(name).update(min=source.min_value,max=source.max_value,description=name)
    objects = []
    for i, (plate, ink) in enumerate(zip(plates, inks)):
        obj = bpy.data.objects.new(f"{i+1:02d} {ink['label']}", bpy.data.meshes.new(f"plate-{i}"))
        bpy.context.scene.collection.objects.link(obj)
        obj.color = tuple(v/255 for v in ink['rgb']) + (1,)
        modifier = obj.modifiers.new("Editable painting recipe", "NODES")
        modifier.node_group = group
        modifier[sockets["Plate"]] = image_from_plate(ink["label"], plate)
        modifier[sockets["Canvas width mm"]], modifier[sockets["Canvas height mm"]] = width, height
        modifier[sockets["Rotation degrees"]] = [0,90,45,-45,22.5,-22.5][i%6]
        modifier[sockets["Seed"]] = i + 100
        for name in values:
            identifier = sockets[name]
            modifier[identifier] = values[name]
            driver = modifier.driver_add(f'["{identifier}"]').driver
            variable = driver.variables.new()
            variable.name = "control"
            variable.targets[0].id = controls
            variable.targets[0].data_path = f'["{name}"]'
            driver.expression = "control"
        objects.append(obj)
    manifests = []
    for recipe, name, tool_width in [(0,"hatch",1.1),(1,"curve",2.5),(2,"stamp",4.0)]:
        controls["Recipe 0 hatch 1 curve 2 stamp"] = recipe
        controls["Width mm"] = tool_width
        controls.update_tag()
        bpy.context.view_layer.update()
        counts = export_svg(objects, inks, width, height, args.out / f"{name}.svg")
        manifests.append({"recipe":name,"width_mm":width,"height_mm":height,"controls":{k:controls[k] for k in values},"polygons_per_plate":counts})
    # A real parameter-change check: spacing must change evaluated mark counts.
    controls["Spacing mm"] = 5.0
    controls.update_tag()
    bpy.context.view_layer.update()
    changed = export_svg(objects, inks, width, height, args.out / "stamp-wide-spacing.svg")
    assert sum(changed) < sum(manifests[-1]["polygons_per_plate"]), "Spacing did not affect evaluated output"
    controls["Spacing mm"] = 3.0
    controls.update_tag()
    bpy.context.view_layer.update()
    bpy.context.view_layer.objects.active = objects[0]
    objects[0].select_set(True)
    bpy.context.scene["prototype"] = "Native editable image sampling and tool instancing. SVG uses evaluated polygons in mm; physical paint calibration is not established."
    bpy.context.scene["painting_inks_json"] = json.dumps(inks)
    bpy.context.scene["painting_objects_json"] = json.dumps([obj.name for obj in objects])
    bpy.context.scene["painting_width_mm"] = width
    bpy.context.scene["painting_height_mm"] = height
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_distance = height * 1.1
                area.spaces.active.region_3d.view_location = (0,0,0)
                area.spaces.active.region_3d.view_rotation = (1,0,0,0)
                area.spaces.active.region_3d.view_perspective = "ORTHO"
                area.spaces.active.shading.color_type = "OBJECT"
    bpy.ops.wm.save_as_mainfile(filepath=str((args.out / "painting-recipes.blend").resolve()),compress=True)
    (args.out / "recipes.json").write_text(json.dumps({"blender":bpy.app.version_string,"recipes":manifests,"spacing_check_passed":True},indent=2)+"\n")
    print(json.dumps({"out":str(args.out),"recipes":[m["recipe"] for m in manifests],"spacing_check":"passed"}))
