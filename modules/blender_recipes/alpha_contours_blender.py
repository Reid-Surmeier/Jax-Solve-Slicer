"""Editable Blender Geometry Nodes study driven by the solved alpha contours."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import bpy


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/prototypes/pepsi-jax-one-black"


def evaluated_paths(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    # Blender's evaluated Curve.data still exposes the source points. Converting
    # the evaluated object to a mesh gives the actual Geometry Nodes result.
    mesh = evaluated.to_mesh()
    neighbors = {v.index: [] for v in mesh.vertices}
    for edge in mesh.edges:
        a, b = edge.vertices
        neighbors[a].append(b); neighbors[b].append(a)
    remaining = {tuple(sorted(edge.vertices)) for edge in mesh.edges}
    paths = []
    while remaining:
        ends = [i for i, links in neighbors.items() if len(links) == 1 and
                tuple(sorted((i, links[0]))) in remaining]
        current = ends[0] if ends else next(iter(remaining))[0]
        start = current
        path = [current]
        while True:
            choices = [n for n in neighbors[current] if tuple(sorted((current, n))) in remaining]
            if not choices: break
            nxt = choices[0]
            remaining.remove(tuple(sorted((current, nxt))))
            path.append(nxt)
            current = nxt
            if current == start: break
        paths.append(path)
    elements = []
    for path in paths:
        points = [(float(mesh.vertices[i].co.x), 304.8 - float(mesh.vertices[i].co.y)) for i in path]
        if len(points) < 2: continue
        data = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in points)
        elements.append(f'<path d="{data}"/>')
    result = (elements, len(mesh.vertices))
    evaluated.to_mesh_clear()
    return result


def write_svg(name, elements):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="228.6mm" height="304.8mm" '
           'viewBox="0 0 228.6 304.8" fill="none" stroke="black" stroke-width="3" '
           'stroke-linejoin="round" stroke-linecap="round">' + "".join(elements) + '</svg>\n')
    path = OUT / name
    path.write_text(svg)
    assert len(ET.parse(path).getroot().findall("{http://www.w3.org/2000/svg}path")) == len(elements)
    return path


def add_lattice(contour_elements):
    plan = json.loads((OUT / "lattice-plan.json").read_text())
    svg_sha = hashlib.sha256((OUT / "contour-study.svg").read_bytes()).hexdigest()
    if svg_sha != plan["contour_svg_sha256"]:
        raise ValueError("Lattice plan is stale; evaluate contours and regenerate it")
    curve = bpy.data.curves.new("Generated links and 9x12 frame", "CURVE")
    curve.dimensions = "3D"
    for points in [plan["frame_mm"], *plan["links_mm"]]:
        spline = curve.splines.new("POLY")
        spline.points.add(len(points)-1)
        for p, (x, y) in zip(spline.points, points): p.co = (x, 304.8-y, 0, 1)
    obj = bpy.data.objects.new("JAX lattice | links and 9x12 frame", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    links, points = evaluated_paths(obj)
    write_svg("connected-lattice.svg", contour_elements + links)
    return {"link_and_frame_svg_paths": len(links), "link_evaluated_points": points}


def build(with_lattice=False):
    data = json.loads((OUT / "source-contours.json").read_text())
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = .001
    curve = bpy.data.curves.new("JAX black alpha contours", "CURVE")
    curve.dimensions = "3D"
    for points in data["contours_mm"]:
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for p, (x, y) in zip(spline.points, points): p.co = (x, 304.8-y, 0, 1)
        spline.use_cyclic_u = points[0] == points[-1]
    obj = bpy.data.objects.new("JAX black plate contours", curve)
    bpy.context.scene.collection.objects.link(obj)
    group = bpy.data.node_groups.new("JAX plate | contour controls", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    spacing = group.interface.new_socket(name="Sample spacing mm", in_out="INPUT", socket_type="NodeSocketFloat")
    spacing.default_value = 1.0; spacing.min_value = .25; spacing.max_value = 5
    smooth = group.interface.new_socket(name="Smooth iterations", in_out="INPUT", socket_type="NodeSocketInt")
    smooth.default_value = 2; smooth.min_value = 0; smooth.max_value = 10
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes = group.nodes; link = group.links.new
    entry = nodes.new("NodeGroupInput"); entry.location = (-500, 0)
    sample = nodes.new("GeometryNodeResampleCurve"); sample.mode = "LENGTH"; sample.location = (-250, 0)
    link(entry.outputs["Geometry"], sample.inputs["Curve"])
    link(entry.outputs["Sample spacing mm"], sample.inputs["Length"])
    position = nodes.new("GeometryNodeInputPosition"); position.location = (-250, -220)
    blur = nodes.new("GeometryNodeBlurAttribute"); blur.data_type = "FLOAT_VECTOR"; blur.location = (0, -180)
    link(position.outputs["Position"], blur.inputs["Value"])
    link(entry.outputs["Smooth iterations"], blur.inputs["Iterations"])
    change = nodes.new("GeometryNodeSetPosition"); change.location = (250, 0)
    link(sample.outputs["Curve"], change.inputs["Geometry"])
    link(blur.outputs["Value"], change.inputs["Position"])
    output = nodes.new("NodeGroupOutput"); output.location = (480, 0)
    link(change.outputs["Geometry"], output.inputs["Geometry"])
    modifier = obj.modifiers.new("Geometry Nodes | editable contour controls", "NODES")
    modifier.node_group = group
    image = bpy.data.images.load(str(OUT / "black-composite.png")); image.pack()
    bpy.context.view_layer.update()
    contour_elements, contour_points = evaluated_paths(obj)
    write_svg("contour-study.svg", contour_elements)
    receipt = {"svg_paths": len(contour_elements), "evaluated_points": contour_points}
    if with_lattice:
        receipt.update(add_lattice(contour_elements))
    receipt.update({"blender_version": bpy.app.version_string, "source_contours": len(data["contours_mm"]),
                    "alpha_image_packed": bool(image.packed_file), "node_group": group.name,
                    "sample_spacing_mm": 1, "smooth_iterations": 2,
                    "known_limit": "Multiple independent contours; overlaps at nominal 3 mm; not a valid one-pass toolpath"})
    (OUT / "blender-contour-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / ("jax-connected-lattice.blend" if with_lattice else "jax-contour-study.blend")))
    print("JAX_CONTOUR_BLENDER", json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-lattice", action="store_true")
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    build(with_lattice=parser.parse_args(args).with_lattice)
