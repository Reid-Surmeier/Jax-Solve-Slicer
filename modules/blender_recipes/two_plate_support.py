"""Generate a source-clipped shading lattice and verify centerline fusion."""

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

from connect_lattice import H, W, SCALE, adjacent, components


OUT = Path(__file__).resolve().parents[2] / "docs/prototypes/pepsi-two-plate-lattice"


def svg_paths(path):
    root = ET.parse(path).getroot()
    if root.get("width") != "228.6mm" or root.get("height") != "304.8mm":
        raise ValueError("Expected the 9 × 12 inch millimetre page")
    return [[tuple(float(v) for v in token.split(",")) for token in item.get("d", "").split()[1::2]]
            for item in root.findall(".//{http://www.w3.org/2000/svg}path")]


def raster(paths, width):
    image = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(image)
    for path in paths:
        if len(path) >= 2:
            draw.line([(x*SCALE,y*SCALE) for x,y in path], fill=0, width=width)
    return image


def mm(x, y):
    return [round(x/SCALE, 3), round(y/SCALE, 3)]


def shade_lines(pitch_px):
    green = np.asarray(Image.open(OUT / "green-alpha16.png"), dtype=np.float32)/65535
    blue = np.asarray(Image.open(OUT / "blue-alpha16.png"), dtype=np.float32)/65535
    edges = []
    for row in green:
        xs = np.flatnonzero(row > .08)
        edges.append((int(xs[0]), int(xs[-1])))
    paths = []
    # Regular diagonal shading clipped by the solved green plate.
    for c in range(-905, 1811, pitch_px):
        run = []
        for y in range(906):
            x = y+c
            if 0 <= x < 906 and edges[y][0]+2 <= x <= edges[y][1]-2 and blue[y,x] < .25:
                run.append((x,y))
            else:
                if len(run) > 10:
                    paths.append([mm(run[0][0],run[0][1]+151),mm(run[-1][0],run[-1][1]+151)])
                run = []
        if len(run) > 10:
            paths.append([mm(run[0][0],run[0][1]+151),mm(run[-1][0],run[-1][1]+151)])
    return paths


def anchored_shading(paths, contours):
    """Keep ribs with two contour contacts and trim unsupported free ends."""
    existing = np.asarray(raster(contours,3)) < 128
    result = []
    for path in paths:
        a,b = [(x*SCALE,y*SCALE) for x,y in path]
        length = max(1,round(math.dist(a,b)))
        hits = []
        for i in range(length+1):
            x = round(a[0]+(b[0]-a[0])*i/length)
            y = round(a[1]+(b[1]-a[1])*i/length)
            if 0 <= x < W and 0 <= y < H and existing[y,x]: hits.append(i)
        groups = []
        for i in hits:
            if not groups or i-groups[-1][-1] > 8: groups.append([i])
            else: groups[-1].append(i)
        if len(groups) < 2: continue
        start = max(0,groups[0][0]-6)
        end = min(length,groups[-1][-1]+6)
        result.append([mm(a[0]+(b[0]-a[0])*start/length,a[1]+(b[1]-a[1])*start/length),
                       mm(a[0]+(b[0]-a[0])*end/length,a[1]+(b[1]-a[1])*end/length)])
    return result


def frame_ties(contour_paths):
    all_points = [p for path in contour_paths for p in path]
    ties = []
    for side_x in (1.5, 227.1):
        for y in (91.4, 213.4):
            near = min(all_points, key=lambda p: (p[0]-side_x)**2+(p[1]-y)**2)
            dx,dy = near[0]-side_x,near[1]-y
            length = math.hypot(dx,dy)
            # Cross the contour centerline by 3 mm for a fused stroke intersection.
            ties.append([[side_x,y],[round(near[0]+3*dx/length,3),round(near[1]+3*dy/length,3)]])
    return ties


def centerline_links(paths):
    mask = np.asarray(raster(paths,2)) < 128
    labels,sizes = components(mask)
    main = int(np.argmax(sizes[1:])+1)
    main_pixels = np.flatnonzero(labels == main).astype(np.int32)
    origin = np.full(labels.size,-1,dtype=np.int32)
    origin[main_pixels] = main_pixels
    queue = deque(main_pixels.tolist())
    found = {}
    while queue and len(found) < len(sizes)-2:
        i = queue.popleft()
        for j in adjacent(i):
            if origin[j] >= 0: continue
            origin[j] = origin[i]
            island = int(labels[j])
            if island and island != main:
                found.setdefault(island,(j,int(origin[i])))
            else:
                queue.append(j)
    if len(found) != len(sizes)-2:
        raise RuntimeError("Some centerline islands have no planned connection")
    links = []
    for island,anchor in found.values():
        x0,y0 = island%W,island//W
        x1,y1 = anchor%W,anchor//W
        dx,dy = x1-x0,y1-y0
        length=math.hypot(dx,dy)
        if not length: continue
        reach=3*SCALE
        links.append([mm(x0-reach*dx/length,y0-reach*dy/length),
                      mm(x1+reach*dx/length,y1+reach*dy/length)])
    return links,len(sizes)-1


def plan(pitch_mm=20.2):
    pitch_px = max(12, round(pitch_mm*SCALE))
    source = OUT / "two-plate-contours.svg"
    contours = svg_paths(source)
    frame = [[1.5,1.5],[227.1,1.5],[227.1,303.3],[1.5,303.3],[1.5,1.5]]
    shade = anchored_shading(shade_lines(pitch_px),contours)
    ties = frame_ties(contours)
    base = contours+[frame]+shade+ties
    links,before = centerline_links(base)
    result = {"source": "two separately solved JAX plates and green-plate silhouette",
              "contour_svg_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "canvas_mm": [228.6,304.8], "stroke_width_mm": 3,
              "shading_pitch_mm": round(pitch_px/SCALE,3), "shading_paths": len(shade), "frame_ties": len(ties),
              "centerline_components_before_links": before,"centerline_links":len(links),
              "paths_mm": [frame]+shade+ties+links}
    (OUT / "support-plan.json").write_text(json.dumps(result,indent=2)+"\n")
    review = raster(contours,2).convert("RGB")
    draw = ImageDraw.Draw(review)
    for path in [frame]+shade+ties:
        draw.line([(x*SCALE,y*SCALE) for x,y in path], fill=(20,120,160), width=3)
    for path in links:
        draw.line([(x*SCALE,y*SCALE) for x,y in path], fill=(215,45,20), width=4)
    review.save(OUT / "support-review.png")
    print(json.dumps({k:v for k,v in result.items() if k!="paths_mm"}))


def verify():
    paths=svg_paths(OUT/"merged-material.svg")
    counts={}
    for width in (2,4,8,12):
        image=raster(paths,width)
        _labels,sizes=components(np.asarray(image)<128)
        counts[f"{width}px"] = len(sizes)-1
        if width==12:image.save(OUT/"merged-material-3mm.png")
    points=[p for path in paths for p in path]
    bounds=[min(x for x,y in points)-1.5,min(y for x,y in points)-1.5,
            max(x for x,y in points)+1.5,max(y for x,y in points)+1.5]
    inside=all((bounds[0]>=0,bounds[1]>=0,bounds[2]<=228.6,bounds[3]<=304.8))
    result={"svg_paths":len(paths),"material_components_by_raster_stroke_width":counts,
            "nominal_stroke_mm":3,"deposited_bounds_mm":[round(v,3) for v in bounds],
            "inside_9x12_inch_envelope":inside,
            "centerline_connected":counts["2px"]==1,
            "nominal_material_connected":counts["12px"]==1,
            "physical_strength_verified":False}
    (OUT/"material-evaluation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    if not inside or counts["2px"]!=1 or counts["12px"]!=1:
        raise RuntimeError("Unattached material remains in the linework")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("plan","verify"))
    parser.add_argument("--pitch-mm",type=float,default=20.2)
    args=parser.parse_args()
    if args.pitch_mm<=0:parser.error("pitch must be positive")
    plan(args.pitch_mm) if args.action=="plan" else verify()
