"""Geometric checks for the throwaway 3 mm one-path prototype."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parents[2]/'docs/prototypes/pepsi-single-pass'
P=json.loads((OUT/'path.json').read_text())
svg=ET.parse(OUT/'single-path.svg').getroot()
paths=svg.findall('{http://www.w3.org/2000/svg}path')
assert len(paths)==1 and paths[0].get('d','').count('M ')==1
points=[tuple(float(v) for v in token.split(',')) for token in paths[0].get('d','').split()[1::2]]
W,H=P['canvas_mm'];radius=P['tool_width_mm']/2


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def intersect(a,b,c,d):
    eps=1e-8
    v=(cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b))
    if v[0]*v[1]<-eps and v[2]*v[3]<-eps:return True
    for p,q,r,s in ((a,b,c,d),(c,d,a,b)):
        if abs(cross(p,q,r))<eps and min(p[0],q[0])-eps<=r[0]<=max(p[0],q[0])+eps and min(p[1],q[1])-eps<=r[1]<=max(p[1],q[1])+eps:return True
    return False

def point_to_segment(p,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)

def segment_distance(a,b,c,d):
    if intersect(a,b,c,d):return 0
    return min(point_to_segment(p,x,y) for p,x,y in ((a,c,d),(b,c,d),(c,a,b),(d,a,b)))

lengths=[0.]
for a,b in zip(points,points[1:]):lengths.append(lengths[-1]+math.dist(a,b))
minimum=1e9;closest=None;crossings=[]
for i in range(len(points)-1):
    a,b=points[i:i+2]
    for j in range(i+2,len(points)-1):
        c,d=points[j:j+2]
        if intersect(a,b,c,d):crossings.append([i,j])
        if lengths[j]-lengths[i+1]<=8:continue
        dist=segment_distance(a,b,c,d)
        if dist<minimum:minimum=dist;closest=[i,j]
assert svg.get('width')=='228.6mm' and svg.get('height')=='304.8mm'
bounds=[min(p[0] for p in points)-radius,min(p[1] for p in points)-radius,
        max(p[0] for p in points)+radius,max(p[1] for p in points)+radius]
assert bounds[0]>=0 and bounds[1]>=0 and bounds[2]<=W and bounds[3]<=H
assert not crossings, f'centerline crossing segments: {crossings[:5]}'
assert minimum>=P['tool_width_mm'], f'deposited nonlocal passes too close: {minimum}'
result={'open_svg_paths':1,'centerline_crossings':len(crossings),'path_length_mm':round(lengths[-1],2),
        'minimum_nonlocal_centerline_separation_mm':round(minimum,3),
        'local_run_exclusion_mm':8,'closest_segment_indices':closest,
        'deposited_bounds_mm':[round(v,3) for v in bounds],
        'inside_9x12_inch_envelope':True,
        'meaning':'No distinct segments separated by >8 mm along the route are closer than the 3 mm tool width; adjacent continuous deposition is excluded.'}
(OUT/'geometry-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
