"""Build editable two-plate contours and merged lattice in Blender."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alpha_contours_blender import evaluated_paths  # noqa: E402


OUT = Path(__file__).resolve().parents[2] / "docs/prototypes/pepsi-two-plate-lattice"


def make_curve(name, paths):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    for points in paths:
        spline = curve.splines.new("POLY")
        spline.points.add(len(points)-1)
        for p, (x,y) in zip(spline.points,points): p.co=(x,304.8-y,0,1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def contour_controls(obj, name):
    group = bpy.data.node_groups.new(f"{name} plate | contour controls", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    spacing = group.interface.new_socket(name="Sample spacing mm", in_out="INPUT", socket_type="NodeSocketFloat")
    spacing.default_value = 1; spacing.min_value = .25; spacing.max_value = 5
    smooth = group.interface.new_socket(name="Smooth iterations", in_out="INPUT", socket_type="NodeSocketInt")
    smooth.default_value = 2; smooth.min_value = 0; smooth.max_value = 10
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    entry=group.nodes.new("NodeGroupInput")
    sample=group.nodes.new("GeometryNodeResampleCurve");sample.mode="LENGTH"
    pos=group.nodes.new("GeometryNodeInputPosition")
    blur=group.nodes.new("GeometryNodeBlurAttribute");blur.data_type="FLOAT_VECTOR"
    move=group.nodes.new("GeometryNodeSetPosition")
    output=group.nodes.new("NodeGroupOutput")
    link=group.links.new
    link(entry.outputs["Geometry"],sample.inputs["Curve"])
    link(entry.outputs["Sample spacing mm"],sample.inputs["Length"])
    link(pos.outputs["Position"],blur.inputs["Value"])
    link(entry.outputs["Smooth iterations"],blur.inputs["Iterations"])
    link(sample.outputs["Curve"],move.inputs["Geometry"])
    link(blur.outputs["Value"],move.inputs["Position"])
    link(move.outputs["Geometry"],output.inputs["Geometry"])
    modifier=obj.modifiers.new("Geometry Nodes | contour controls", "NODES")
    modifier.node_group=group
    return group.name


def save_svg(name, paths):
    svg=('<svg xmlns="http://www.w3.org/2000/svg" width="228.6mm" height="304.8mm" '
         'viewBox="0 0 228.6 304.8" fill="none" stroke="black" stroke-width="3" '
         'stroke-linecap="round" stroke-linejoin="round"><g id="one-black-plastic-layer">'
         +''.join(paths)+'</g></svg>\n')
    dest=OUT/name;dest.write_text(svg)
    assert len(ET.parse(dest).getroot().findall(".//{http://www.w3.org/2000/svg}path"))==len(paths)
    return dest


def build(with_lattice=False):
    data=json.loads((OUT/"plate-contours.json").read_text())
    bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system="METRIC"
    bpy.context.scene.unit_settings.scale_length=.001
    all_paths=[];receipt={"blender_version":bpy.app.version_string,"plates":{}}
    for name in ("blue","green"):
        obj=make_curve(f"JAX {name} plate | source contours",data["paths_mm"][name])
        node=contour_controls(obj,name)
        bpy.context.view_layer.update()
        paths,points=evaluated_paths(obj)
        all_paths.extend(paths)
        receipt["plates"][name]={"source_paths":len(data["paths_mm"][name]),"evaluated_paths":len(paths),
                                 "evaluated_points":points,"geometry_nodes":node}
        image=bpy.data.images.load(str(OUT/f"{name}-alpha16.png"));image.pack()
    save_svg("two-plate-contours.svg",all_paths)
    if with_lattice:
        plan=json.loads((OUT/"support-plan.json").read_text())
        sha=hashlib.sha256((OUT/"two-plate-contours.svg").read_bytes()).hexdigest()
        if sha!=plan["contour_svg_sha256"]:raise ValueError("Support plan is stale")
        support=make_curve("JAX merged material | frame and source-derived shading",plan["paths_mm"])
        bpy.context.view_layer.update()
        paths,points=evaluated_paths(support)
        all_paths.extend(paths)
        save_svg("merged-material.svg",all_paths)
        receipt["support"]={"source_paths":len(plan["paths_mm"]),"evaluated_paths":len(paths),
                            "evaluated_points":points}
    (OUT/"blender-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/("merged-material.blend" if with_lattice else "two-plate-contours.blend")))
    print("TWO_PLATE_BLENDER",json.dumps(receipt),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-lattice",action="store_true")
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    build(parser.parse_args(args).with_lattice)
