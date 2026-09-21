"""Plan source-derived contour links, then verify one connected 3 mm lattice."""

import json
import hashlib
from collections import deque
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw


OUT = Path(__file__).resolve().parents[2] / "docs/prototypes/pepsi-jax-one-black"
W, H = 906, 1209
SCALE = W / 228.6


def adjacent(i):
    x = i % W
    if i >= W:
        yield i-W
        if x: yield i-W-1
        if x < W-1: yield i-W+1
    if i < W*(H-1):
        yield i+W
        if x: yield i+W-1
        if x < W-1: yield i+W+1
    if x: yield i-1
    if x < W-1: yield i+1


def components(mask):
    flat = mask.ravel()
    labels = np.zeros(flat.size, dtype=np.uint16)
    sizes = [0]
    for raw in np.flatnonzero(flat):
        seed = int(raw)
        if labels[seed]: continue
        number = len(sizes)
        sizes.append(0)
        labels[seed] = number
        queue = deque([seed])
        while queue:
            i = queue.popleft()
            sizes[number] += 1
            for j in adjacent(i):
                if flat[j] and not labels[j]:
                    labels[j] = number
                    queue.append(j)
    return labels, sizes


def xy(i):
    return [i % W, i // W]


def mm(point):
    return [round(point[0] / SCALE, 3), round(point[1] / SCALE, 3)]


def plan():
    svg_sha = hashlib.sha256((OUT / "contour-study.svg").read_bytes()).hexdigest()
    mask = np.asarray(Image.open(OUT / "contour-3mm.png").convert("L")) < 128
    labels, sizes = components(mask)
    main = int(np.argmax(sizes[1:]) + 1)
    main_pixels = np.flatnonzero(labels == main).astype(np.int32)
    origin = np.full(labels.size, -1, dtype=np.int32)
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
                found.setdefault(island, (j, int(origin[i])))
            else:
                queue.append(j)
    if len(found) != len(sizes)-2:
        raise RuntimeError(f"Found links for {len(found)} of {len(sizes)-2} islands")
    links = [[mm(xy(island)), mm(xy(anchor))] for island, anchor in found.values()]
    main_yx = np.column_stack(np.unravel_index(main_pixels, (H, W)))
    for target in ((6, H//2), (W-7, H//2)):
        distances = (main_yx[:, 1]-target[0])**2 + (main_yx[:, 0]-target[1])**2
        nearest = main_pixels[int(np.argmin(distances))]
        links.append([mm(target), mm(xy(int(nearest)))])
    frame = [[1.5, 1.5], [227.1, 1.5], [227.1, 303.3], [1.5, 303.3], [1.5, 1.5]]
    receipt = {"source": "evaluated Blender contour-3mm.png", "contour_svg_sha256": svg_sha, "tool_width_mm": 3,
               "components_before": len(sizes)-1, "island_links": len(found),
               "frame_links": 2, "frame_mm": frame, "links_mm": links}
    (OUT / "lattice-plan.json").write_text(json.dumps(receipt, indent=2) + "\n")
    review = Image.open(OUT / "contour-hairline.png").convert("RGB")
    draw = ImageDraw.Draw(review)
    draw.line([(x*SCALE, y*SCALE) for x,y in frame], fill=(220, 40, 20), width=3)
    for link in links:
        draw.line([(x*SCALE, y*SCALE) for x,y in link], fill=(220, 40, 20), width=4)
    review.save(OUT / "lattice-links-review.png")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("links_mm", "frame_mm")}))


def verify():
    root = ET.parse(OUT / "connected-lattice.svg").getroot()
    if root.get("width") != "228.6mm" or root.get("height") != "304.8mm":
        raise ValueError("SVG is not 9 × 12 inches in millimetres")
    image = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(image)
    overlap_count = np.zeros((H, W), dtype=np.uint16)
    all_points = []
    paths = root.findall("{http://www.w3.org/2000/svg}path")
    for path in paths:
        points = [tuple(float(v) for v in token.split(",")) for token in path.get("d", "").split()[1::2]]
        if len(points) < 2: raise ValueError("Empty SVG path")
        all_points.extend(points)
        pixel_points = [(x*SCALE, y*SCALE) for x, y in points]
        draw.line(pixel_points, fill=0, width=12)
        path_mask = Image.new("1", (W, H))
        ImageDraw.Draw(path_mask).line(pixel_points, fill=1, width=12)
        overlap_count += np.asarray(path_mask, dtype=np.uint16)
    image.save(OUT / "connected-lattice-3mm.png")
    _labels, sizes = components(np.asarray(image) < 128)
    bounds = [min(x for x,y in all_points)-1.5, min(y for x,y in all_points)-1.5,
              max(x for x,y in all_points)+1.5, max(y for x,y in all_points)+1.5]
    inside = bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= 228.6 and bounds[3] <= 304.8
    result = {"svg_paths": len(paths), "deposited_components": len(sizes)-1,
              "distinct_path_footprint_overlap_pixels": int(np.count_nonzero(overlap_count >= 2)),
              "deposited_bounds_mm": [round(v,3) for v in bounds],
              "inside_9x12_inch_envelope": inside,
              "connected_lattice": len(sizes) == 2 and inside,
              "one_continuous_nonoverlapping_toolpath": len(paths) == 1 and not np.any(overlap_count >= 2) and inside}
    (OUT / "lattice-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if not result["connected_lattice"]: raise RuntimeError("Deposited lattice remains disconnected")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("plan", "verify"):
        raise SystemExit("usage: connect_lattice.py plan|verify")
    (plan if sys.argv[1] == "plan" else verify)()
