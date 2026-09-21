"""Trace both JAX plates as provisional centerlines for one plastic layer."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from alpha_contours import contours


OUT = Path(__file__).resolve().parents[2] / "docs/prototypes/pepsi-two-plate-lattice"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blue-threshold", type=float, default=.3)
    parser.add_argument("--green-threshold", type=float, default=.3)
    parser.add_argument("--blur-px", type=float, default=.7)
    args = parser.parse_args()
    if not 0 < args.blue_threshold < 1 or not 0 < args.green_threshold < 1 or args.blur_px < 0:
        parser.error("thresholds must be between 0 and 1; blur must be nonnegative")
    plate_paths = {}
    preview = Image.new("RGB", (906, 1209), "white")
    draw = ImageDraw.Draw(preview)
    thresholds = {"blue": args.blue_threshold, "green": args.green_threshold}
    for name, color in (("blue", (0, 65, 170)), ("green", (0, 135, 85))):
        alpha = np.asarray(Image.open(OUT / f"{name}-alpha16.png"), dtype=np.float32)/65535
        softened = Image.fromarray(np.uint8(np.round(alpha*255))).filter(ImageFilter.GaussianBlur(args.blur_px))
        paths = contours(np.asarray(softened) >= round(thresholds[name]*255))
        mm_paths = []
        for path in paths:
            mm_path = [[round(u*.5*228.6/906, 4), round(38.1+v*.5*228.6/906, 4)] for u,v in path]
            mm_paths.append(mm_path)
            draw.line([(x*906/228.6, y*906/228.6) for x,y in mm_path], fill=color, width=2)
        plate_paths[name] = mm_paths
    receipt = {"source": "separate blue-target and green-target JAX alpha plates", "thresholds": thresholds,
               "blur_px": args.blur_px, "canvas_mm": [228.6, 304.8],
               "paths_mm": plate_paths,
               "path_counts": {name: len(paths) for name,paths in plate_paths.items()}}
    (OUT / "plate-contours.json").write_text(json.dumps(receipt))
    preview.save(OUT / "two-plate-contours-review.png")
    print(receipt["path_counts"])


if __name__ == "__main__": main()
