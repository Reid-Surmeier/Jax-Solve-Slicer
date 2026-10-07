"""Prototype (issue 20): picture -> SVG outlines for the direction-colour plate.

Outlines are the edges of the dark drawn strokes. Run with system Python:
    python3 vectorize.py IMAGE OUT.svg --crop X0 Y0 X1 Y1 [--width-mm 200]
"""
import argparse

import cv2
import numpy as np

UP = 4  # upsample before thresholding so stroke edges are not pixel stairs


def outlines(image, crop, dark=90, min_area_px=30):
    x0, y0, x1, y1 = crop
    bgr = cv2.imread(image)[y0:y1, x0:x1]
    value = bgr.max(axis=2)  # a stroke is dark in every channel
    value = cv2.resize(value, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    value = cv2.GaussianBlur(value, (0, 0), UP * 0.6)
    mask = (value < dark).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    keep = [cv2.approxPolyDP(c, 0.35 * UP, True)[:, 0, :] / UP
            for c in contours if cv2.contourArea(c) >= min_area_px * UP * UP]
    return [c for c in keep if len(c) >= 3], (x1 - x0, y1 - y0), mask


def write_svg(path, loops, size_px, width_mm):
    w, h = size_px
    s = width_mm / w
    with open(path, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*s:.3f}mm" '
                f'height="{h*s:.3f}mm" viewBox="0 0 {w*s:.3f} {h*s:.3f}">\n')
        for loop in loops:
            d = " L".join(f"{x*s:.3f},{y*s:.3f}" for x, y in loop)
            f.write(f'<path d="M{d} Z" fill="none" stroke="black" stroke-width="0.1"/>\n')
        f.write("</svg>\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("svg")
    ap.add_argument("--crop", type=int, nargs=4, required=True)
    ap.add_argument("--width-mm", type=float, default=200.0)
    ap.add_argument("--debug-png")
    a = ap.parse_args()
    loops, size, mask = outlines(a.image, a.crop)
    assert loops, "no dark strokes found: check --crop and the threshold"
    write_svg(a.svg, loops, size, a.width_mm)
    if a.debug_png:
        cv2.imwrite(a.debug_png, 255 - mask * 255)
    print(f"{len(loops)} outlines, {sum(len(l) for l in loops)} points, "
          f"plate {a.width_mm:.1f} x {a.width_mm * size[1] / size[0]:.1f} mm")
