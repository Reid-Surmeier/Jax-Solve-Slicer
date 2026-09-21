"""Throwaway stencil-to-one-path experiment for issue 12; run with Python + Pillow."""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parents[2] / 'docs/prototypes/pepsi-single-pass'
PX = 3
WIDTH_MM, HEIGHT_MM, TOOL_MM = 228.6, 304.8, 3.0
W, H = round(WIDTH_MM * PX), round(HEIGHT_MM * PX)
BITMAP = {
 'P': ('11111','10001','10000','11110','10000','10000','10000'),
 'E': ('11111','10000','10000','11110','10000','10000','11111'),
 'S': ('11111','10000','10000','11111','00001','00001','11111'),
 'I': ('11111','00100','00100','00100','00100','00100','11111'),
 'C': ('11111','10000','10000','10000','10000','10000','11111'),
 'U': ('10001','10001','10001','10001','10001','10001','11111'),
 'M': ('10001','11011','11111','10001','10001','10001','10001'),
 'B': ('11111','10001','10000','11111','10001','10000','11110'),
 'R': ('11111','10001','10000','11110','10110','10011','10001'),
}


def draw_word(draw: ImageDraw.ImageDraw, word: str, center_mm: float, top_mm: float,
              cell_mm: float) -> dict:
    cell=round(cell_mm*PX); width=(6*len(word)-1)*cell
    x=round(center_mm*PX-width/2); y=round(top_mm*PX)
    for index,letter in enumerate(word):
        for row,bits in enumerate(BITMAP[letter]):
            for col,on in enumerate(bits):
                if on=='1':
                    a=x+(index*6+col)*cell; b=y+row*cell
                    draw.rectangle((a,b,a+cell,b+cell),fill=255)
    bottom=y+7*cell
    base_h=round(4.2*PX)
    draw.rectangle((x,bottom,x+width,bottom+base_h),fill=255)
    for index,letter in enumerate(word):
        if letter in ('M','R'):
            center=x+(index*6+2.5)*cell
            draw.rectangle((center-2.5*PX,bottom,center+2.5*PX,bottom+base_h),fill=0)
    return {'text':word,'x':x,'top':y,'bottom':bottom,'width':width,'cell_px':cell}

def make_mask():
    mask = Image.new('L', (W,H))
    d = ImageDraw.Draw(mask)
    words = [draw_word(d,'PEPSI',114.3,40,5.8),
             draw_word(d,'ICE',114.3,190,6.0),
             draw_word(d,'CUCUMBER',119.3,242,4.1)]
    # The globe is a disc with a winding bay open to its right. Its outline remains one stencil boundary.
    cx,cy,rx,ry = 114.3*PX,143*PX,48*PX,41*PX
    d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry), fill=255)
    slit=[]
    for i in range(181):
        t=i/180
        x=(cx+rx+8*PX)*(1-t)+(cx-rx+7*PX)*t
        y=cy+10*PX*math.sin(2.2*math.pi*t+0.3) - 1*PX*t
        slit.append((round(x),round(y)))
    d.line(slit,fill=0,width=round(6.0*PX),joint='curve')
    for x,y in slit[::3]: d.ellipse((x-9,y-9,x+9,y+9),fill=0)
    # A narrow trunk and four arms connect globe and the three word rows.
    spine_x=round(10*PX)
    d.line((spine_x,words[0]['top']+16*PX,spine_x,words[2]['bottom']),fill=255,width=round(4.5*PX))
    branches=[(words[0]['top']+25*PX,words[0]['x']+16*PX),
              (round(143*PX),round((114.3-48+3)*PX)),
              (words[1]['bottom']-2*PX,words[1]['x']+10*PX),
              (words[2]['bottom']-2*PX,words[2]['x']+10*PX)]
    for y,x in branches:
        d.line((spine_x,y,x,y),fill=255,width=round(4.5*PX))
    return mask,words


def contours(mask: Image.Image):
    pix=mask.load(); edges=defaultdict(list)
    for y in range(H):
        for x in range(W):
            if pix[x,y] < 128: continue
            if y==0 or pix[x,y-1]<128: edges[x,y].append((x+1,y))
            if x==W-1 or pix[x+1,y]<128: edges[x+1,y].append((x+1,y+1))
            if y==H-1 or pix[x,y+1]<128: edges[x+1,y+1].append((x,y+1))
            if x==0 or pix[x-1,y]<128: edges[x,y+1].append((x,y))
    loops=[]
    while edges:
        start=next(iter(edges)); pts=[start]; here=start; last_dir=(1,0)
        while True:
            out=edges[here]
            if len(out)==1: nxt=out.pop()
            else:
                # At a diagonal contact, keep the occupied pixel on the right.
                dx,dy=last_dir
                dirs=((dy,-dx),(dx,dy),(-dy,dx),(-dx,-dy))
                nxt=min(out,key=lambda p:dirs.index((p[0]-here[0],p[1]-here[1])))
                out.remove(nxt)
            if not out: del edges[here]
            last_dir=(nxt[0]-here[0],nxt[1]-here[1]); here=nxt
            if here==start: break
            pts.append(here)
        loops.append(pts)
    return sorted(loops,key=len,reverse=True)


def simplify(points, tolerance=1.0):
    # Ramer-Douglas-Peucker, preserving the ordered open curve.
    keep={0,len(points)-1}; todo=[(0,len(points)-1)]; t2=tolerance*tolerance
    while todo:
        i,j=todo.pop(); ax,ay=points[i]; bx,by=points[j]; dx=bx-ax;dy=by-ay; den=dx*dx+dy*dy
        best=0; idx=None
        for k in range(i+1,j):
            x,y=points[k]; u=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/den)) if den else 0
            ds=(x-ax-u*dx)**2+(y-ay-u*dy)**2
            if ds>best: best=ds;idx=k
        if best>t2:
            keep.add(idx);todo.extend(((i,idx),(idx,j)))
    return [points[k] for k in sorted(keep)]


def open_loop(loop):
    # Remove a 7 mm run on the straight left side of the spine.
    x0=min(x for x,y in loop)
    candidates=[i for i,(x,y) in enumerate(loop) if x==x0 and 115*PX<y<168*PX]
    if not candidates: raise ValueError('No straight trunk side for safe opening')
    pivot=min(candidates,key=lambda i:abs(loop[i][1]-143*PX))
    rotated=loop[pivot:]+loop[:pivot]
    # Keep the longer of the two traversal directions; 7 mm opening remains between endpoints.
    gap=round(7*PX)
    assert all(p[0]==x0 for p in rotated[-gap:]), 'opening left the straight trunk'
    return simplify(rotated[:-gap],1.3)


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    mask,words=make_mask()
    loops=contours(mask)
    if len(loops)!=1: raise ValueError(f"Expected one contour, found {len(loops)}")
    loop,cuts=loops[0],[]
    mask.save(HERE/'stencil.png')
    raw=open_loop(loop)
    points=[(round(x/PX,3),round(y/PX,3)) for x,y in raw]
    length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    # A single open path; no other SVG geometry is exported.
    d='M '+' L '.join(f'{x:.3f},{y:.3f}' for x,y in points)
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="228.6mm" height="304.8mm" '
         f'viewBox="0 0 228.6 304.8"><path d="{d}" fill="none" stroke="#132d68" '
         f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>\n')
    (HERE/'single-path.svg').write_text(svg)
    preview=Image.new('RGB',(W,H),'#f8f5ea');dr=ImageDraw.Draw(preview)
    pixpts=[(round(x*PX),round(y*PX)) for x,y in points]
    dr.line(pixpts,fill='#132d68',width=round(TOOL_MM*PX),joint='curve')
    r=round(TOOL_MM*PX/2)
    for x,y in (pixpts[0],pixpts[-1]):dr.ellipse((x-r,y-r,x+r,y+r),fill='#132d68')
    preview.save(HERE/'preview.png')
    data={'canvas_mm':[WIDTH_MM,HEIGHT_MM],'tool_width_mm':TOOL_MM,'source':'source.png',
          'path_points_mm':points,'word_layout':words,'counter_cuts':cuts,
          'length_mm':round(length,2),'one_open_path':True,'blender_version':'4.3.2'}
    (HERE/'path.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:v for k,v in data.items() if k not in ('path_points_mm','word_layout')},indent=2))

if __name__=='__main__':main()
