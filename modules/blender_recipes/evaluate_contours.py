"""Render the evaluated Blender SVG and measure 3 mm inter-contour overlap."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw


OUT = Path(__file__).resolve().parents[2] / "docs/prototypes/pepsi-jax-one-black"
W, H = 906, 1209
SCALE = W / 228.6


def main():
    root = ET.parse(OUT / "contour-study.svg").getroot()
    assert root.get("width") == "228.6mm" and root.get("height") == "304.8mm"
    paths = root.findall("{http://www.w3.org/2000/svg}path")
    assert paths
    count = np.zeros((H, W), dtype=np.uint16)
    hairline = Image.new("L", (W, H), 255)
    thin = ImageDraw.Draw(hairline)
    all_points = []
    for path in paths:
        mm = [tuple(float(v) for v in token.split(",")) for token in path.get("d", "").split()[1::2]]
        all_points.extend(mm)
        xy = [(x * SCALE, y * SCALE) for x, y in mm]
        assert len(xy) >= 2
        thin.line(xy, fill=0, width=2)
        mask = Image.new("1", (W, H))
        ImageDraw.Draw(mask).line(xy, fill=1, width=12)
        count += np.asarray(mask, dtype=np.uint16)
    hairline.save(OUT / "contour-hairline.png")
    Image.fromarray(np.where(count > 0, 0, 255).astype(np.uint8)).save(OUT / "contour-3mm.png")
    bounds = [min(x for x, y in all_points) - 1.5, min(y for x, y in all_points) - 1.5,
              max(x for x, y in all_points) + 1.5, max(y for x, y in all_points) + 1.5]
    inside = bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= 228.6 and bounds[3] <= 304.8
    receipt = {
        "source": "Blender Geometry Nodes evaluated contour-study.svg",
        "svg_paths": len(paths),
        "required_svg_paths": 1,
        "distinct_contour_footprint_overlap_pixels": int(np.count_nonzero(count >= 2)),
        "deposited_pixels": int(np.count_nonzero(count)),
        "nominal_tool_width_mm": 3,
        "deposited_bounds_mm": [round(v, 3) for v in bounds],
        "inside_9x12_inch_canvas": inside,
        "one_pass_valid": len(paths) == 1 and not np.any(count >= 2) and inside,
    }
    (OUT / "path-evaluation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__": main()
