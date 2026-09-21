"""Throwaway green-plate infill variations for issue 12."""

import argparse
import json

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, label

from two_plate_support import OUT, SCALE, centerline_links, components, mm, raster, svg_paths


def clipped_runs(mask, mode, pitch):
    paths = []

    def add(points):
        run = []
        for x, y in points:
            if 0 <= x < 906 and 0 <= y < 906 and mask[y, x]:
                run.append((x, y))
            else:
                if len(run) >= 20:
                    paths.append([mm(run[0][0], run[0][1] + 151),
                                  mm(run[-1][0], run[-1][1] + 151)])
                run = []
        if len(run) >= 20:
            paths.append([mm(run[0][0], run[0][1] + 151),
                          mm(run[-1][0], run[-1][1] + 151)])

    if mode == "horizontal":
        for y in range(0, 906, pitch):
            add((x, y) for x in range(907))
    elif mode == "rising":
        for c in range(-905, 906, pitch):
            add((y + c, y) for y in range(907))
    else:
        for c in range(0, 1811, pitch):
            add((c - y, y) for y in range(907))
    return paths


def plan():
    green = np.asarray(Image.open(OUT / "green-alpha16.png"), dtype=np.float32) / 65535
    blue = np.asarray(Image.open(OUT / "blue-alpha16.png"), dtype=np.float32) / 65535
    mask = binary_erosion((green >= .20) & (green > blue * .75), iterations=5)
    regions, _ = label(mask)
    sizes = np.bincount(regions.ravel())
    mask &= sizes[regions] >= 350
    base = svg_paths(OUT / "merged-material.svg")
    variants = {
        "parallel": [("horizontal", 24)],
        "diagonal": [("rising", 32)],
        "crosshatch": [("rising", 48), ("falling", 48)],
    }
    for name, recipe in variants.items():
        infill = [path for mode, pitch in recipe for path in clipped_runs(mask, mode, pitch)]
        links, before = centerline_links(base + infill)
        result = {"green_alpha_threshold": .20, "blue_exclusion_ratio": .75,
                  "inset_px": 5, "minimum_region_px": 350,
                  "recipe": recipe, "infill_paths": len(infill),
                  "components_before_links": before, "anchor_links": len(links),
                  "paths_mm": infill + links}
        (OUT / f"green-infill-{name}-plan.json").write_text(json.dumps(result, indent=2) + "\n")
        print(name, {k: v for k, v in result.items() if k != "paths_mm"}, flush=True)


def review():
    rows = []
    for name in ("parallel", "diagonal", "crosshatch"):
        plan_data = json.loads((OUT / f"green-infill-{name}-plan.json").read_text())
        paths = svg_paths(OUT / f"green-infill-{name}.svg")
        base_count = 147
        assert len(paths) == base_count + len(plan_data["paths_mm"])
        counts = {f"{width}px": len(components(np.asarray(raster(paths, width)) < 128)[1]) - 1
                  for width in (2, 12)}
        assert counts == {"2px": 1, "12px": 1}, (name, counts)
        black = raster(paths, 12)
        black.save(OUT / f"green-infill-{name}-black.png")
        colored = raster(paths[:base_count], 12).convert("RGB")
        draw = ImageDraw.Draw(colored)
        for path in paths[base_count:base_count + plan_data["infill_paths"]]:
            draw.line([(x * SCALE, y * SCALE) for x, y in path], fill=(0, 150, 65), width=12)
        for path in paths[base_count + plan_data["infill_paths"]:]:
            draw.line([(x * SCALE, y * SCALE) for x, y in path], fill=(230, 110, 0), width=12)
        colored.save(OUT / f"green-infill-{name}-review.png")
        rows.append((name, colored, {"svg_paths": len(paths), "infill_paths": plan_data["infill_paths"],
                                    "anchor_links": plan_data["anchor_links"], "components": counts}))
    sheet = Image.new("RGB", (3 * 465, 640), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (name, colored, _) in enumerate(rows):
        sheet.paste(colored.resize((453, 604)), (index * 465 + 6, 29))
        draw.text((index * 465 + 12, 8), name.title(), fill="black")
    sheet.save(OUT / "green-infill-comparison.png")
    (OUT / "green-infill-evaluation.json").write_text(
        json.dumps({"green_alpha_threshold": .20, "variants": {name: result for name, _, result in rows},
                    "physical_strength_verified": False, "single_route_verified": False}, indent=2) + "\n")
    print({name: result for name, _, result in rows})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "review"))
    args = parser.parse_args()
    plan() if args.action == "plan" else review()
