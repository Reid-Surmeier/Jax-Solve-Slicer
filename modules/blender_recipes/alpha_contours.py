"""Extract one image-derived contour level from the solved black alpha plate."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/prototypes/pepsi-jax-one-black"


def contours(mask):
    """Trace threshold crossings on the pixel grid; each edge has one shared key."""
    edges = {}
    height, width = mask.shape
    for y in range(height - 1):
        for x in range(width - 1):
            a, b, c, d = bool(mask[y, x]), bool(mask[y, x + 1]), bool(mask[y + 1, x + 1]), bool(mask[y + 1, x])
            crossing = []
            if a != b: crossing.append((2*x+1, 2*y))
            if b != c: crossing.append((2*x+2, 2*y+1))
            if c != d: crossing.append((2*x+1, 2*y+2))
            if d != a: crossing.append((2*x, 2*y+1))
            if len(crossing) == 2:
                pairs = [(crossing[0], crossing[1])]
            elif len(crossing) == 4:
                pairs = [(crossing[0], crossing[1]), (crossing[2], crossing[3])]
            else:
                pairs = []
            for u, v in pairs:
                edges.setdefault(u, []).append(v)
                edges.setdefault(v, []).append(u)
    unvisited = {tuple(sorted((u, v))) for u, vs in edges.items() for v in vs}
    result = []
    while unvisited:
        u, v = next(iter(unvisited))
        start = u if len(edges[u]) == 1 else v if len(edges[v]) == 1 else u
        path = [start]
        current = start
        while True:
            choices = [n for n in edges[current] if tuple(sorted((current, n))) in unvisited]
            if not choices: break
            nxt = choices[0]
            unvisited.remove(tuple(sorted((current, nxt))))
            path.append(nxt)
            current = nxt
            if current == start: break
        if len(path) >= 30: result.append(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=.4)
    parser.add_argument("--blur-px", type=float, default=.7)
    args = parser.parse_args()
    if not 0 < args.threshold < 1 or args.blur_px < 0:
        parser.error("threshold must be between 0 and 1, and blur must be nonnegative")
    alpha = np.asarray(Image.open(OUT / "black-alpha16.png"), dtype=np.float32) / 65535
    smooth = np.asarray(Image.fromarray(np.uint8(np.round(alpha * 255))).filter(ImageFilter.GaussianBlur(args.blur_px))) / 255
    paths = contours(smooth >= args.threshold)
    mm_per_pixel = 228.6 / alpha.shape[1]
    out = {
        "source": "black-alpha16.png",
        "threshold": args.threshold,
        "blur_px": args.blur_px,
        "width_mm": 228.6,
        "height_mm": 304.8,
        "tool_width_mm": 3,
        "contours_mm": [[[round(u*.5*mm_per_pixel, 4), round(38.1+v*.5*mm_per_pixel, 4)] for u, v in path] for path in paths],
    }
    (OUT / "source-contours.json").write_text(json.dumps(out))
    print({"contours": len(paths), "points": sum(map(len, paths))})


if __name__ == "__main__":
    main()
