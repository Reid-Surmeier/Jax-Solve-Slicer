"""Issue 12 throwaway Blender scene: editable path plus flat 3 mm GN footprint."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import bpy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/prototypes/pepsi-single-pass'
PATH=OUT/'path.json'
SVG=OUT/'single-path.svg'
BLEND=OUT/'single-path.blend'


def export_svg_from_scene(output=None):
    obj=bpy.data.objects['EDIT PATH | one start, one end']
    if obj.type!='CURVE' or len(obj.data.splines)!=1:
        raise ValueError('Expected one Blender curve spline')
    spline=obj.data.splines[0]
    if spline.use_cyclic_u: raise ValueError('Curve must remain open')
    points=[(round(p.co.x,3),round(304.8-p.co.y,3)) for p in spline.points]
    if len(points)<2:raise ValueError('Path is empty')
    d='M '+' L '.join(f'{x:.3f},{y:.3f}' for x,y in points)
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="228.6mm" height="304.8mm" '
         f'viewBox="0 0 228.6 304.8"><path d="{d}" fill="none" stroke="#132d68" '
         f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>\n')
    destination=Path(output) if output is not None else SVG
    destination.write_text(svg)
    root=ET.fromstring(svg)
    assert len(root.findall('{http://www.w3.org/2000/svg}path'))==1
    return {'svg':str(destination),'splines':1,'cyclic':False,'points':len(points),
            'start_mm':points[0],'end_mm':points[-1],
            'bounds_mm':[min(x for x,y in points),min(y for x,y in points),
                         max(x for x,y in points),max(y for x,y in points)]}


def build():
    data=json.loads(PATH.read_text());points=data['path_points_mm']
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for ng in list(bpy.data.node_groups):
        if ng.name.startswith('Single path |'):bpy.data.node_groups.remove(ng)
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.001
    scene['prototype']='Issue 12: one color, one open path, 3 mm tool; do not send to machine'
    scene['canvas_mm']='228.6 x 304.8'
    scene['source_image']='Packed supplied Pepsi Ice Cucumber screenshot'
    curve=bpy.data.curves.new('One continuous centerline','CURVE');curve.dimensions='3D';curve.resolution_u=1
    spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
    for p,(x,y) in zip(spline.points,points):p.co=(x,304.8-y,0,1)
    spline.use_cyclic_u=False
    obj=bpy.data.objects.new('EDIT PATH | one start, one end',curve)
    scene.collection.objects.link(obj)
    obj['contact_width_mm']=3.0
    obj['edit_hint']='Tab to Edit Mode; move curve points, then export saved curve with this script'
    mat=bpy.data.materials.new('Single dark blue deposit');mat.diffuse_color=(.02,.08,.32,1)
    mat.use_nodes=True
    node=mat.node_tree.nodes.get('Principled BSDF')
    if node:node.inputs['Base Color'].default_value=(.02,.08,.32,1)
    ng=bpy.data.node_groups.new('Single path | flat deposited width','GeometryNodeTree')
    ng.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    width=ng.interface.new_socket(name='Tool width mm',in_out='INPUT',socket_type='NodeSocketFloat')
    width.default_value=3.0;width.min_value=.5;width.max_value=10.0
    ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n=ng.nodes;ln=ng.links.new
    gi=n.new('NodeGroupInput');gi.location=(-650,0)
    half=n.new('ShaderNodeMath');half.operation='MULTIPLY';half.inputs[1].default_value=.5;half.location=(-430,-170)
    ln(gi.outputs['Tool width mm'],half.inputs[0])
    profile=n.new('GeometryNodeCurvePrimitiveCircle');profile.inputs['Resolution'].default_value=12;profile.location=(-230,-170)
    ln(half.outputs[0],profile.inputs['Radius'])
    sweep=n.new('GeometryNodeCurveToMesh');sweep.location=(0,0)
    ln(gi.outputs['Geometry'],sweep.inputs['Curve']);ln(profile.outputs['Curve'],sweep.inputs['Profile Curve'])
    pos=n.new('GeometryNodeInputPosition');pos.location=(0,-180)
    flat=n.new('ShaderNodeVectorMath');flat.operation='MULTIPLY';flat.inputs[1].default_value=(1,1,0);flat.location=(180,-180)
    ln(pos.outputs['Position'],flat.inputs[0])
    flatten=n.new('GeometryNodeSetPosition');flatten.location=(400,0)
    ln(sweep.outputs['Mesh'],flatten.inputs['Geometry']);ln(flat.outputs['Vector'],flatten.inputs['Position'])
    material=n.new('GeometryNodeSetMaterial');material.inputs['Material'].default_value=mat;material.location=(590,0)
    ln(flatten.outputs['Geometry'],material.inputs['Geometry'])
    go=n.new('NodeGroupOutput');go.location=(790,0);ln(material.outputs['Geometry'],go.inputs['Geometry'])
    mod=obj.modifiers.new('GN | 3 mm contact preview','NODES');mod.node_group=ng
    # Retain the supplied image in the project without showing it over the vector preview.
    img=bpy.data.images.load(str(OUT/'source.png'));img.pack()
    ref=bpy.data.objects.new('Reference | supplied image (hidden)',None)
    ref.empty_display_type='IMAGE';ref.data=img;ref.empty_display_size=220
    ref.location=(114.3,152.4,-1);ref.hide_viewport=True;ref.hide_render=True
    scene.collection.objects.link(ref)
    for name,(x,y) in [('START | path begins',points[0]),('END | path ends',points[-1])]:
        marker=bpy.data.objects.new(name,None);marker.empty_display_type='SPHERE';marker.empty_display_size=2.5
        marker.location=(x,304.8-y,0.4);scene.collection.objects.link(marker)
    # Top view keeps the physical envelope visible when the file opens.
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_perspective='ORTHO'
                area.spaces.active.region_3d.view_distance=365
                area.spaces.active.region_3d.view_location=(114.3,152.4,0)
                area.spaces.active.region_3d.view_rotation=(1,0,0,0)
    bpy.context.view_layer.update()
    mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    assert mesh is not None and len(mesh.vertices)>0
    zrange=max(v.co.z for v in mesh.vertices)-min(v.co.z for v in mesh.vertices)
    assert zrange<1e-5, f'footprint is not flat: {zrange}'
    receipt=export_svg_from_scene()
    receipt.update({'blender_version':bpy.app.version_string,'node_group':ng.name,'preview_vertices':len(mesh.vertices),
                    'flat_z_range_mm':zrange,'packed_reference_image':bool(img.packed_file)})
    (OUT/'blender-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    print('JAX_SINGLE_PATH_SCENE',json.dumps(receipt),flush=True)

if __name__=='__main__':build()
