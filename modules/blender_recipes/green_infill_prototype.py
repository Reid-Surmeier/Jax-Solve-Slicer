"""Throwaway green-plate infill variations for issue 12."""

import argparse
import json
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt, label

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


def green_mask():
    green = np.asarray(Image.open(OUT / "green-alpha16.png"), dtype=np.float32) / 65535
    blue = np.asarray(Image.open(OUT / "blue-alpha16.png"), dtype=np.float32) / 65535
    mask = binary_erosion((green >= .20) & (green > blue * .75), iterations=5)
    regions, _ = label(mask)
    sizes = np.bincount(regions.ravel())
    mask &= sizes[regions] >= 350
    return mask


def plan():
    mask = green_mask()
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


def wide_frame_ties():
    support = json.loads((OUT / "support-plan.json").read_text())
    start = 1 + support["shading_paths"]
    ties = support["paths_mm"][start:start + support["frame_ties"]]
    assert len(ties) == 4
    paths = []
    for (x0, y0), (x1, y1) in ties:
        # Seven overlapping 3 mm nozzle tracks form an 18 mm wide tie.
        for offset in (-7.5, -5, -2.5, 0, 2.5, 5, 7.5):
            paths.append([[x0, round(y0 + offset, 3)], [x1, round(y1 + offset, 3)]])
        paths.extend(([[x0, y0 - 7.5], [x0, y0 + 7.5]],
                      [[x1, y1 - 7.5], [x1, y1 + 7.5]]))
    return paths


def connect_all(paths):
    """Attach nested contour islands to the nearest connected centerline."""
    links = []
    while True:
        mask = np.asarray(raster(paths + links, 2)) < 128
        labels, sizes = components(mask)
        labels = labels.reshape(mask.shape)
        if len(sizes) == 2:
            return links
        main = int(np.argmax(sizes[1:]) + 1)
        distance, nearest = distance_transform_edt(labels != main, return_indices=True)
        other = (labels > 0) & (labels != main)
        y, x = np.unravel_index(np.argmin(np.where(other, distance, np.inf)), labels.shape)
        near_y, near_x = nearest[:, y, x]
        links.append([mm(x, y), mm(int(near_x), int(near_y))])


def final_plan():
    mask = green_mask()
    y, x = np.ogrid[:906, :906]
    # Clear the two text fields; leave upper-body and side hatching.
    mask[(y >= 500) & (y < 745) & (x >= 215) & (x <= 700)] = False
    mask[(y >= 745) & (x >= 90) & (x <= 810)] = False
    mask[y[:, 0] >= 880, :] = False
    infill = clipped_runs(mask, "horizontal", 24)
    wide_ties = wide_frame_ties()
    contours = svg_paths(OUT / "two-plate-contours.svg")
    frame = json.loads((OUT / "support-plan.json").read_text())["paths_mm"][0]
    material = contours + [frame] + infill + wide_ties
    _labels, sizes = components(np.asarray(raster(material, 2)) < 128)
    before = len(sizes) - 1
    links = connect_all(material)
    result = {"source": "solved green alpha, with ICE and CUCUMBER keep-clear fields",
              "green_alpha_threshold": .20, "pitch_mm": 6.0,
              "ice_keep_clear_px": [215, 500, 700, 745],
              "cucumber_keep_clear_px": [90, 745, 810, 906],
              "infill_paths": len(infill), "wide_tie_paths": len(wide_ties),
              "tie_width_mm": 18, "tie_count": 4, "frame_mm": frame,
              "components_before_links": before, "anchor_links": len(links),
              "longest_anchor_link_mm": round(max(math.dist(*path) for path in links), 3),
              "paths_mm": infill + wide_ties + links}
    (OUT / "green-infill-parallel-final-plan.json").write_text(json.dumps(result, indent=2) + "\n")
    print({k: v for k, v in result.items() if k != "paths_mm"}, flush=True)


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


def final_review():
    name = "parallel-final"
    plan_data = json.loads((OUT / f"green-infill-{name}-plan.json").read_text())
    paths = svg_paths(OUT / f"green-infill-{name}.svg")
    base_count = 79
    assert len(paths) == base_count + len(plan_data["paths_mm"])
    counts = {f"{width}px": len(components(np.asarray(raster(paths, width)) < 128)[1]) - 1
              for width in (2, 12)}
    assert counts == {"2px": 1, "12px": 1}, counts
    points = [point for path in paths for point in path]
    bounds = [min(x for x, _ in points) - 1.5, min(y for _, y in points) - 1.5,
              max(x for x, _ in points) + 1.5, max(y for _, y in points) + 1.5]
    assert bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= 228.6 and bounds[3] <= 304.8
    raster(paths, 12).save(OUT / f"green-infill-{name}-black.png")
    colored = raster(paths[:base_count], 12).convert("RGB")
    draw = ImageDraw.Draw(colored)
    first = base_count
    second = first + plan_data["infill_paths"]
    third = second + plan_data["wide_tie_paths"]
    for segment, color in ((paths[first:second], (0, 150, 65)),
                           (paths[second:third], (20, 85, 200)),
                           (paths[third:], (230, 110, 0))):
        for path in segment:
            draw.line([(x * SCALE, y * SCALE) for x, y in path], fill=color, width=12)
    colored.save(OUT / f"green-infill-{name}-review.png")
    result = {"svg_paths": len(paths), "infill_paths": plan_data["infill_paths"],
              "wide_tie_paths": plan_data["wide_tie_paths"], "anchor_links": plan_data["anchor_links"],
              "components": counts, "deposited_bounds_mm": [round(v, 3) for v in bounds],
              "physical_strength_verified": False,
              "single_route_verified": False}
    (OUT / f"green-infill-{name}-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "review", "final-plan", "final-review"))
    args = parser.parse_args()
    {"plan": plan, "review": review, "final-plan": final_plan,
     "final-review": final_review}[args.action]()
