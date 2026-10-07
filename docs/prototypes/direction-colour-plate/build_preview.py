"""Prototype (issue 20): outlines -> landform -> GeoSlicer contours -> beads coloured by heading.

    blender -b --python build_preview.py -- --addon-parent DIR --out DIR [--svg outlines.svg]

1 Blender unit = 1 mm. Without --svg the plate is a bare rectangle and the script
checks the four-tone "envelope" seen on the back of the reference plate.
The contour toolpath comes from the GeoSlicer add-on (toposlice.run, Planar);
everything after it is two Geometry Nodes groups that stay live in the saved file.
"""
import argparse
import math
import re
import sys

import bpy
import numpy as np
from mathutils import Vector


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg")
    ap.add_argument("--addon-parent", required=True, help="folder holding the geoslicer package")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plate", type=float, nargs=2, default=(60.0, 48.0), help="mm, used without --svg")
    ap.add_argument("--bead", type=float, default=0.42)
    ap.add_argument("--layer", type=float, default=0.2)
    ap.add_argument("--grid", type=float, default=0.25, help="landform grid spacing, mm")
    ap.add_argument("--relief", type=float, default=0.03, help="printed height per mm of distance")
    # 30 degrees off the plate's axes, so the four sides of a rectangle print as four tones
    # (light, mid grey, black-grey, black) the way the back of the reference plate does.
    ap.add_argument("--light-from", type=float, default=300.0, help="slopes facing this way print light, degrees")
    ap.add_argument("--slicer-direction", action="store_true", help="keep the add-on's loop direction")
    ap.add_argument("--width-px", type=int, default=2400)
    ap.add_argument("--samples", type=int, default=48)
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:])


# ---- small node helpers -------------------------------------------------

def put(tree, socket, value):
    if isinstance(value, bpy.types.NodeSocket):
        tree.links.new(value, socket)
    elif value is not None:
        socket.default_value = value


def node(tree, kind, inputs=None, **props):
    n = tree.nodes.new(kind)
    for k, v in props.items():
        setattr(n, k, v)
    for k, v in (inputs or {}).items():
        put(tree, n.inputs[k], v)
    return n


def calc(tree, op, a, b=None):
    return node(tree, "ShaderNodeMath", {0: a, 1: b}, operation=op).outputs[0]


def xyz(tree, vec):
    return node(tree, "ShaderNodeSeparateXYZ", {0: vec}).outputs


def vec(tree, x=0.0, y=0.0, z=0.0):
    return node(tree, "ShaderNodeCombineXYZ", {0: x, 1: y, 2: z}).outputs[0]


def group(name, sockets, geometry_in=False):
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    if geometry_in:
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ids = {}
    for label, kind, default in sockets:
        s = tree.interface.new_socket(label, in_out="INPUT", socket_type=kind)
        if default is not None:
            s.default_value = default
        ids[label] = s.identifier
    return tree, tree.nodes.new("NodeGroupInput").outputs, tree.nodes.new("NodeGroupOutput").inputs, ids


def attach(obj, tree, ids, values):
    mod = obj.modifiers.new(tree.name, "NODES")
    mod.node_group = tree
    for label, value in values.items():
        mod[ids[label]] = value
    return mod


# ---- outlines -----------------------------------------------------------

def import_outlines(svg):
    """SVG paths as one curve object in plate millimetres, origin bottom-left."""
    text = open(svg).read()
    w, h = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text).groups())
    pts = np.array([[float(a), float(b)] for a, b in re.findall(r"(-?[\d.]+),(-?[\d.]+)", text)])
    want_lo, want_hi = np.array([pts[:, 0].min(), h - pts[:, 1].max()]), np.array([pts[:, 0].max(), h - pts[:, 1].min()])

    import addon_utils
    addon_utils.enable("io_curve_svg")
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=svg)
    curves = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    with bpy.context.temp_override(active_object=curves[0], selected_editable_objects=curves):
        bpy.ops.object.join()
    obj = curves[0]
    # Fit to the SVG's own numbers so the importer's unit convention does not matter.
    co = np.array([obj.matrix_world @ p.co for s in obj.data.splines for p in (s.bezier_points or s.points)])[:, :2]
    scale = (want_hi - want_lo) / (co.max(0) - co.min(0))
    assert abs(scale[0] / scale[1] - 1) < 0.01, "SVG import changed the aspect ratio"
    obj.matrix_world = obj.matrix_world.Translation((*(want_lo - co.min(0) * scale), 0)) @ \
        obj.matrix_world.Diagonal((scale[0], scale[1], 1, 1)) @ obj.matrix_world
    return obj, w, h


def outlines_object(a):
    if a.svg:
        obj, w, h = import_outlines(a.svg)
    else:
        w, h = a.plate
        obj = bpy.data.objects.new("Outlines", bpy.data.curves.new("Outlines", "CURVE"))
        bpy.context.scene.collection.objects.link(obj)
    obj.name = "Outlines"
    obj.data.dimensions, obj.data.fill_mode = "3D", "FULL"
    # The plate's own edge is an outline too: it gives the border facets.
    inv = obj.matrix_world.inverted()
    border = obj.data.splines.new("POLY")
    border.points.add(3)
    for p, (x, y) in zip(border.points, ((0, 0), (w, 0), (w, h), (0, h))):
        p.co = (*(inv @ Vector((x, y, 0))), 1)
    border.use_cyclic_u = True
    obj.hide_render = True
    return obj, w, h


# ---- geometry nodes -----------------------------------------------------

def landform_group():
    """Height = distance to the nearest outline: a roof with 45 degree slopes."""
    t, gin, gout, ids = group("Landform", [
        ("Outlines", "NodeSocketObject", None), ("Width", "NodeSocketFloat", 200.0),
        ("Height", "NodeSocketFloat", 160.0), ("Grid spacing", "NodeSocketFloat", 0.25)])
    w, h, sp = gin["Width"], gin["Height"], gin["Grid spacing"]
    grid = node(t, "GeometryNodeMeshGrid", {"Size X": w, "Size Y": h,
                "Vertices X": calc(t, "ADD", calc(t, "DIVIDE", w, sp), 1.0),
                "Vertices Y": calc(t, "ADD", calc(t, "DIVIDE", h, sp), 1.0)})
    moved = node(t, "GeometryNodeTransform", {"Geometry": grid.outputs["Mesh"],
                 "Translation": vec(t, calc(t, "DIVIDE", w, 2.0), calc(t, "DIVIDE", h, 2.0))})
    lines = node(t, "GeometryNodeCurveToMesh", {"Curve": node(
        t, "GeometryNodeObjectInfo", {0: gin["Outlines"]}, transform_space="RELATIVE").outputs["Geometry"]})
    near = node(t, "GeometryNodeProximity", {0: lines.outputs["Mesh"]}, target_element="EDGES")
    raised = node(t, "GeometryNodeSetPosition", {"Geometry": moved.outputs[0],
                  "Offset": vec(t, z=near.outputs["Distance"])})
    t.links.new(raised.outputs[0], gout[0])
    return t, ids


def plate_group(filament, base):
    """Toolpath points -> tone from travel direction -> beads on a shallow relief."""
    t, gin, gout, ids = group("Plate", [
        ("Landform", "NodeSocketObject", None), ("Light from", "NodeSocketFloat", 300.0),
        ("Uphill on left", "NodeSocketBool", True), ("Relief", "NodeSocketFloat", 0.03),
        ("Bead width", "NodeSocketFloat", 0.42), ("Layer height", "NodeSocketFloat", 0.2)], geometry_in=True)
    path = node(t, "GeometryNodeMeshToCurve", {"Mesh": gin["Geometry"]}).outputs[0]

    def named(name, kind="FLOAT_VECTOR"):
        return node(t, "GeometryNodeInputNamedAttribute", {"Name": name}, data_type=kind).outputs[0]

    tx, ty, _ = xyz(t, named("tangent"))   # the add-on's travel direction
    nx, ny, _ = xyz(t, named("snormal"))   # landform normal: its XY points downhill
    # cross(tangent, uphill).z > 0 means uphill is on the left of travel. The add-on
    # winds every loop counter-clockwise, so loops round a pit and loops round a peak
    # disagree; reversing one kind makes a slope's facing decide its colour.
    side = calc(t, "SUBTRACT", calc(t, "MULTIPLY", ty, nx), calc(t, "MULTIPLY", tx, ny))
    # Summed over the add-on's own `path` id, not over splines: Mesh to Curve does not
    # promise one spline per loop, and a per-spline average flipped the wrong loops.
    per_loop = node(t, "GeometryNodeAccumulateField", {"Value": side, "Group ID": named("path", "INT")},
                    data_type="FLOAT", domain="POINT").outputs["Total"]
    flip = node(t, "GeometryNodeSwitch", {"Switch": gin["Uphill on left"], "False": 1.0,
                "True": calc(t, "SIGN", per_loop)}, input_type="FLOAT").outputs[0]
    heading = xyz(t, node(t, "ShaderNodeVectorMath", {0: vec(
        t, calc(t, "MULTIPLY", tx, flip), calc(t, "MULTIPLY", ty, flip))}, operation="NORMALIZE").outputs[0])
    axis = calc(t, "RADIANS", calc(t, "ADD", gin["Light from"], 90.0))
    # First guess for the filament: tone follows the cosine of heading against one axis.
    tone = calc(t, "ADD", 0.5, calc(t, "MULTIPLY", 0.5, calc(
        t, "ADD", calc(t, "MULTIPLY", heading[0], calc(t, "COSINE", axis)),
        calc(t, "MULTIPLY", heading[1], calc(t, "SINE", axis)))))
    toned = node(t, "GeometryNodeStoreNamedAttribute", {"Geometry": path, "Name": "tone", "Value": tone},
                 data_type="FLOAT", domain="POINT").outputs[0]

    def on_relief(geometry, lift):
        x, y, z = xyz(t, node(t, "GeometryNodeInputPosition").outputs[0])
        return node(t, "GeometryNodeSetPosition", {"Geometry": geometry, "Position": vec(
            t, x, y, calc(t, "ADD", calc(t, "MULTIPLY", z, gin["Relief"]), lift))}).outputs[0]

    half_h = calc(t, "DIVIDE", gin["Layer height"], 2.0)
    flat = node(t, "GeometryNodeSetCurveNormal", {0: on_relief(toned, half_h)}, mode="Z_UP").outputs[0]
    profile = node(t, "GeometryNodeTransform", {
        "Geometry": node(t, "GeometryNodeCurvePrimitiveCircle", {"Resolution": 8, "Radius": 1.0}).outputs[0],
        "Scale": vec(t, calc(t, "DIVIDE", gin["Bead width"], 2.0), half_h, 1.0)}).outputs[0]
    beads = node(t, "GeometryNodeCurveToMesh", {"Curve": flat, "Profile Curve": profile}).outputs[0]
    beads = node(t, "GeometryNodeSetMaterial", {"Geometry": beads, "Material": filament}).outputs[0]
    under = on_relief(node(t, "GeometryNodeObjectInfo", {0: gin["Landform"]},
                           transform_space="RELATIVE").outputs["Geometry"], 0.0)
    under = node(t, "GeometryNodeSetMaterial", {"Geometry": under, "Material": base}).outputs[0]
    both = node(t, "GeometryNodeJoinGeometry")
    t.links.new(beads, both.inputs[0])
    t.links.new(under, both.inputs[0])
    t.links.new(both.outputs[0], gout[0])
    return t, ids


# ---- look ---------------------------------------------------------------

def materials():
    fil = bpy.data.materials.new("Dual-colour silk")
    fil.use_nodes = True
    nt = fil.node_tree
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "tone"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.006, 0.006, 0.007, 1)   # charcoal half
    ramp.color_ramp.elements[1].color = (0.62, 0.64, 0.67, 1)      # silver half
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value, bsdf.inputs["Roughness"].default_value = 0.2, 0.4
    nt.links.new(tone.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    base = bpy.data.materials.new("Under the beads")
    base.use_nodes = True
    base.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1)
    return fil, base


def stage(scene, w, h, a):
    def aimed(obj, at, to):
        obj.location = at
        obj.rotation_euler = (Vector(to) - Vector(at)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(obj)
        return obj

    centre = (w / 2, h / 2, 0)
    cam = bpy.data.cameras.new("Camera")
    cam.lens, cam.clip_end = 70, 10000
    scene.camera = aimed(bpy.data.objects.new("Camera", cam), (w / 2, h / 2 - 0.45 * w, 2.25 * w), centre)
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy, sun.angle = 2.0, math.radians(12)
    aimed(bpy.data.objects.new("Sun", sun), (-w, 2 * h, 1.2 * w), centre)
    scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.2, 1)
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.use_denoising = a.samples, True
    scene.render.resolution_x, scene.render.resolution_y = a.width_px, int(a.width_px * h / w * 1.05)
    scene.view_settings.view_transform = "Standard"


def check(path, a):
    """A slope's facing must decide its tone, and beads must lie flat.

    On a bare rectangle this is the four-tone envelope on the back of the reference plate.
    """
    mesh = path.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    n = len(mesh.vertices)

    def read(name, k=1):
        out = np.empty(n * k)
        mesh.attributes[name].data.foreach_get("vector" if k == 3 else "value", out)
        return out.reshape(n, k) if k == 3 else out

    beads = read("dist") > 0   # the surface under the beads carries no toolpath attributes
    facing = read("snormal", 3)[beads, :2]
    steep = np.hypot(*facing.T) > 0.5   # leave out ridges and valley floors
    light = math.radians(a.light_from)
    want = 0.5 + 0.5 * (facing[steep] @ (math.cos(light), math.sin(light))) / np.hypot(*facing[steep].T)
    right = np.abs(read("tone")[beads][steep] - want) < 0.1
    print(f"check: {right.mean():.1%} of bead points have the tone their slope's facing asks for")
    assert right.mean() > 0.97, "loops are travelled the wrong way round"
    z = np.empty(n * 3)
    mesh.vertices.foreach_get("co", z)
    z = z[2::3][beads]
    assert z.max() - z.min() < a.layer + a.relief * 60 + 0.05 or a.svg, "beads are standing on edge"


# ---- run ----------------------------------------------------------------

def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    outlines, w, h = outlines_object(a)

    land = bpy.data.objects.new("Landform", bpy.data.meshes.new("Landform"))
    scene.collection.objects.link(land)
    tree, ids = landform_group()
    attach(land, tree, ids, {"Outlines": outlines, "Width": w, "Height": h, "Grid spacing": a.grid})
    land.hide_render = True

    sys.path.insert(0, a.addon_parent)
    import geoslicer
    geoslicer.register()
    s = scene.topo_slicer
    s.target_object, s.use_modifiers, s.strategy = land, True, "PLANAR"
    s.layer_mode, s.max_layer_height = "HEIGHT", a.bead   # 45 degree slopes: one layer = one bead apart
    s.resample_length, s.align_seams, s.make_curves = a.bead * 0.75, True, False
    assert "FINISHED" in bpy.ops.toposlice.run(), "GeoSlicer produced no toolpath"
    path = bpy.data.objects["Landform_toolpath"]
    n = len(path.data.vertices)
    print(f"toolpath: {n} points, {path.data.attributes['dist'].data[n - 1].value / 1000:.1f} m, "
          f"{path.data.attributes['path'].data[n - 1].value + 1} loops")

    tree, ids = plate_group(*materials())
    attach(path, tree, ids, {"Landform": land, "Light from": a.light_from, "Relief": a.relief,
                             "Uphill on left": not a.slicer_direction, "Bead width": a.bead, "Layer height": a.layer})

    if not a.slicer_direction:
        check(path, a)

    stage(scene, w, h, a)
    scene.render.filepath = f"{a.out}/preview.png"
    bpy.ops.wm.save_as_mainfile(filepath=f"{a.out}/plate.blend")
    bpy.ops.render.render(write_still=True)


main()
