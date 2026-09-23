"""PROTOTYPE, throwaway: tool-library style recipes turn JAX alpha plates into tool-labelled SVG.

Five variants of the same alpha stack, one per recipe, so the owner can compare directions:
  A close   — Chuck Close grid: per cell the 3 strongest inks stack sponge / ring / dot
  B drags   — every ink as long directional drags (flat brush for light inks, liner for dark)
  C scatter — every ink as scattered stamped dabs (sponge or leaf) placed by alpha
  D mixed   — one recipe per ink colour (yellow/orange drags, reds leaves, darks liner...)
  E contour — AARON-style: black outlines, round sponge fills each shape in rings following its edge
Tools are digital PLACEHOLDERS until the real tools are scanned. The preview PNG is a raster of the
same mark list (not a physical paint prediction). Python + NumPy + Pillow (+ OpenCV for E only).

Run: python3 docs/prototypes/tool-recipes/prototype_tool_recipes.py
"""
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
ALPHA = HERE.parents[1] / "reproduction/2026-09-20/alpha"
WIDTH_MM = 510.0  # artwork width of the accepted legacy SVG
PX_PER_MM = 2.0   # preview raster resolution


def blob(r, seed, n=28, wobble=0.18):
    rng = np.random.RandomState(seed)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    k = 1 + wobble * np.convolve(np.r_[rng.randn(n), rng.randn(3)], np.ones(4) / 4, "valid")[:n]
    return np.c_[np.cos(t) * r * k, np.sin(t) * r * k]


def lens(length, width, n=24):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[np.cos(t) * length / 2, np.sin(t) * np.abs(np.sin(t)) ** 0.5 * width / 2]


def circle(r, n=32):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[np.cos(t) * r, np.sin(t) * r]


# The tool library. Footprints are fixed (never scaled); a different size is a different tool.
TOOLS = {
    "sponge-L": dict(mode="dab", outline=blob(4.6, 1), per_dip=8, density=0.80, texture=True),
    "sponge-S": dict(mode="dab", outline=blob(2.3, 2), per_dip=12, density=0.85, texture=True),
    "ring-7": dict(mode="dab", outline=circle(3.5), hole=circle(2.0), per_dip=10, density=0.85, rotations=[0]),
    "leaf-6": dict(mode="dab", outline=lens(6.5, 2.6), per_dip=10, density=0.85),
    "flat-12": dict(mode="drag", width=12.0, per_dip=140.0, density=0.62),
    "liner-2": dict(mode="drag", width=1.6, per_dip=260.0, density=0.90),
    "round-8": dict(mode="drag", width=8.0, per_dip=180.0, density=0.55, texture=True),
}

DARK = {"black", "blue_black", "sepia", "royal_blue", "blue", "purple", "burgundy"}


def box(a, r):
    """Mean over a (2r+1)^2 window, edge-clamped."""
    p = np.pad(a, r + 1, mode="edge").cumsum(0).cumsum(1)
    n = 2 * r + 1
    s = p[n:, n:] - p[:-n, n:] - p[n:, :-n] + p[:-n, :-n]
    return (s / n / n)[: a.shape[0], : a.shape[1]]


class Plates:
    def __init__(self):
        with np.load(ALPHA / "alpha_stack_float32.npz") as z:
            self.a = np.clip(z["alpha_stack"], 0, 1)
        self.inks = json.loads((ALPHA / "metadata.json").read_text())["inkset"]["inks"]
        self.mm = WIDTH_MM / self.a.shape[2]
        self.w, self.h = WIDTH_MM, self.a.shape[1] * self.mm
        self.smooth = {}

    def sample(self, p, x, y, radius_mm):
        r = max(1, int(radius_mm / self.mm))
        if (p, r) not in self.smooth:
            self.smooth[p, r] = box(self.a[p], r)
        ix = np.clip((np.asarray(x) / self.mm).astype(int), 0, self.a.shape[2] - 1)
        iy = np.clip((np.asarray(y) / self.mm).astype(int), 0, self.a.shape[1] - 1)
        return self.smooth[p, r][iy, ix]


def length(pts):
    return float(np.linalg.norm(np.diff(np.asarray(pts), axis=0), axis=1).sum())


def dab(plate, tool, x, y, angle=0.0):
    return dict(plate=plate, tool=tool, x=float(x), y=float(y), angle=float(angle))


def drag(plate, tool, pts):
    return dict(plate=plate, tool=tool, pts=[(float(a), float(b)) for a, b in pts])


# ---- recipes: alpha says where/how much, the recipe says which tool and how ----

def recipe_close(P, cell=12.0):
    """45° diamond lattice; each cell stacks the 3 strongest inks as base sponge, ring, centre dot."""
    marks, rng = [], np.random.RandomState(7)
    for row, y in enumerate(np.arange(cell / 4, P.h, cell / 2)):
        for x in np.arange(cell / 4 + (row % 2) * cell / 2, P.w, cell):
            vals = np.array([P.sample(p, x, y, cell * 0.3) for p in range(len(P.inks))])
            order = np.argsort(-vals)
            for rank, (tool, gate) in enumerate([("sponge-L", 0.10), ("ring-7", 0.12), ("sponge-S", 0.10)]):
                p = order[rank]
                if vals[p] > gate:
                    marks.append(dab(int(p), tool, x, y, rng.uniform(0, 360)))
    return marks


def drags_for(P, p, tool, angle_deg, spacing, on, off, min_mm=28.0, step=1.0):
    t = TOOLS[tool]
    a = math.radians(angle_deg)
    d, n = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    c, reach = np.array([P.w / 2, P.h / 2]), math.hypot(P.w, P.h) / 2
    s = np.arange(-reach, reach, step)
    out = []
    for k, off_n in enumerate(np.arange(-reach, reach, spacing)):
        pts = c + off_n * n + s[:, None] * d
        inside = (pts[:, 0] >= 0) & (pts[:, 0] <= P.w) & (pts[:, 1] >= 0) & (pts[:, 1] <= P.h)
        v = np.where(inside, P.sample(p, pts[:, 0], pts[:, 1], t["width"] / 2), 0)
        start, run = None, 0.0
        for i in range(len(s)):
            live = v[i] > (off if start is not None else on)
            if start is None and live:
                start, run = i, 0.0
            elif start is not None:
                run += step
                if not live or run >= t["per_dip"] or i == len(s) - 1:
                    if run >= min_mm:
                        seg = pts[start:i + 1]
                        out.append(drag(p, tool, seg[[0, -1]] if k % 2 == 0 else seg[[-1, 0]]))
                    start = i if live else None
                    run = 0.0
    return out


def area(poly):
    x, y = poly.T
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def scatter_for(P, p, tool, angle_deg, fill=0.8, jitter=35.0, seed=0):
    """Place dabs where the ink is; enough dabs to cover `fill` of the plate's alpha area."""
    rng = np.random.RandomState(1000 + p + seed)
    a = P.a[p]
    count = int(a.sum() * P.mm * P.mm * fill / area(TOOLS[tool]["outline"]))
    w = np.clip(box(a, 2) - 0.08, 0, None) ** 1.5  # cluster dabs where the ink is strong
    prob = (w / w.sum()).ravel()
    idx = rng.choice(prob.size, size=count, p=prob)
    ys, xs = np.divmod(idx, a.shape[1])
    xs = (xs + rng.rand(count)) * P.mm
    ys = (ys + rng.rand(count)) * P.mm
    return [dab(p, tool, x, y, angle_deg + rng.uniform(-jitter, jitter)) for x, y in zip(xs, ys)]


def recipe_drags(P):
    marks = []
    for p, ink in enumerate(P.inks):
        ang = 68 + (p % 4 - 1.5) * 5
        if ink["role"] in DARK:
            marks += drags_for(P, p, "liner-2", ang, 2.6, on=0.22, off=0.12)
        else:
            marks += drags_for(P, p, "flat-12", ang, 11.0, on=0.22, off=0.12)
    return marks


def recipe_scatter(P):
    marks = []
    for p, ink in enumerate(P.inks):
        if ink["role"] in DARK:
            marks += scatter_for(P, p, "leaf-6", 60 + p * 11)
        else:
            marks += scatter_for(P, p, "sponge-L", 0, jitter=180)
    return marks


MIXED = {  # the "per colour toolpath" idea: each ink gets its own recipe
    "yellow": ("drag", "flat-12", 70), "orange": ("drag", "flat-12", 62),
    "rose": ("scatter", "sponge-L", 0), "fresh_green": ("scatter", "sponge-S", 0),
    "purple": ("scatter", "sponge-S", 0), "sepia": ("scatter", "sponge-L", 0),
    "red": ("scatter", "leaf-6", 40), "burgundy": ("scatter", "leaf-6", 40),
    "black": ("drag", "liner-2", 74), "blue_black": ("drag", "liner-2", 66),
    "blue": ("drag", "liner-2", 80), "royal_blue": ("drag", "liner-2", 60),
}


def recipe_mixed(P):
    marks = []
    for p, ink in enumerate(P.inks):
        kind, tool, ang = MIXED[ink["role"]]
        if kind == "drag":
            spacing = 11.0 if tool == "flat-12" else 3.4
            marks += drags_for(P, p, tool, ang, spacing, on=0.24, off=0.14)
        else:
            marks += scatter_for(P, p, tool, ang, jitter=180 if tool != "leaf-6" else 30)
    return marks


def recipe_contour(P, up=4):
    """AARON-style: black outlines each shape, other inks fill shapes with a round sponge in rings that follow the edge inward."""
    import cv2  # PROTOTYPE-only dependency (already installed); contour tracing + distance transform
    marks, s = [], P.mm / up
    for p, ink in enumerate(P.inks):
        a = np.asarray(Image.fromarray(box(P.a[p], 5)).resize((P.a.shape[2] * up, P.a.shape[1] * up), Image.BILINEAR))
        region = (a > 0.2).astype(np.uint8)
        region = cv2.morphologyEx(region, cv2.MORPH_OPEN, np.ones((17, 17), np.uint8))
        if ink["role"] in {"black", "blue_black"}:
            rings, tool = [region], "liner-2"
        else:
            dist = cv2.distanceTransform(region, cv2.DIST_L2, 5) * s  # mm to the shape's edge
            gap = TOOLS["round-8"]["width"] * 0.8
            rings = [(dist > gap / 2 + k * gap).astype(np.uint8) for k in range(int(dist.max() // gap) + 1)]
            tool = "round-8"
        for ring in rings:
            for c in cv2.findContours(ring, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
                c = cv2.approxPolyDP(c, 2, True)[:, 0, :].astype(float) * s
                if len(c) > 2 and length(np.r_[c, c[:1]]) > 20:
                    pts = np.r_[c, c[:1]]
                    for i in range(0, len(pts) - 1, 24):  # split long rings so a dip can run out mid-shape
                        marks.append(drag(p, tool, pts[i:i + 25]))
    return marks


VARIANTS = {"A-close": recipe_close, "B-drags": recipe_drags, "C-scatter": recipe_scatter, "D-mixed": recipe_mixed, "E-contour": recipe_contour}


# ---- execution order: per plate, per tool, serpentine rows; new dip every per_dip ----

def sequence(marks, row_mm=10.0):
    def key(m):
        x, y = (m["x"], m["y"]) if "x" in m else m["pts"][0]
        r = int(y // row_mm)
        return (m["plate"], m["tool"], r, x if r % 2 == 0 else -x)
    marks.sort(key=key)
    used, dip, last = 0.0, 0, None
    for i, m in enumerate(marks):
        t = TOOLS[m["tool"]]
        cost = 1.0 if t["mode"] == "dab" else length(m["pts"])
        if (m["plate"], m["tool"]) != last or used + cost > t["per_dip"]:
            dip, used, last = dip + 1, 0.0, (m["plate"], m["tool"])
        used += cost
        m["dip"], m["seq"] = dip, i
    return marks


def outline(m):
    t = TOOLS[m["tool"]]
    a = math.radians(m["angle"])
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return [(pts @ rot.T + [m["x"], m["y"]]) for pts in [t["outline"]] + ([t["hole"]] if "hole" in t else [])]


def hexrgb(rgb):
    return "#" + "".join(f"{v:02x}" for v in rgb)


def write_svg(P, name, marks, path):
    f = lambda v: f"{v:.2f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(P.w)}mm" height="{f(P.h)}mm" viewBox="0 0 {f(P.w)} {f(P.h)}">',
           "<metadata>" + json.dumps({"prototype": name, "tools": "PLACEHOLDER digital footprints, not scanned",
                                      "note": "preview opacity is a stand-in, not a physical paint prediction"}) + "</metadata>",
           '<rect width="100%" height="100%" fill="#fff"/>', "<defs>"]
    for tid, t in TOOLS.items():
        if t["mode"] == "dab":
            d = " ".join("M " + " L ".join(f"{f(x)},{f(y)}" for x, y in ring) + " Z" for ring in [t["outline"]] + ([t["hole"]] if "hole" in t else []))
            out.append(f'<symbol id="tool-{tid}" overflow="visible"><path d="{d}" fill="currentColor" fill-rule="evenodd"/></symbol>')
    out.append("</defs>")
    for p, ink in enumerate(P.inks):
        col = hexrgb(ink["rgb"])
        out.append(f'<g id="plate-{p:02d}-{ink["role"]}" data-ink="{ink["id"]}" color="{col}">')
        for m in (m for m in marks if m["plate"] == p):
            t = TOOLS[m["tool"]]
            attrs = f'data-tool="{m["tool"]}" data-mode="{t["mode"]}" data-dip="{m["dip"]}" data-seq="{m["seq"]}" opacity="{t["density"]}"'
            if t["mode"] == "dab":
                out.append(f'<use href="#tool-{m["tool"]}" transform="translate({f(m["x"])} {f(m["y"])}) rotate({m["angle"]:.1f})" {attrs}/>')
            else:
                d = "M " + " L ".join(f"{f(x)},{f(y)}" for x, y in m["pts"])
                out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{t["width"]}" stroke-linecap="round" stroke-linejoin="round" {attrs}/>')
        out.append("</g>")
    out.append("</svg>")
    path.write_text("\n".join(out))


def preview(P, marks):
    """Raster of the same mark list: per-plate coverage, then the legacy over-compositing in ink order."""
    W, H = int(P.w * PX_PER_MM), int(P.h * PX_PER_MM)
    rng = np.random.RandomState(3)
    sponge = np.asarray(Image.fromarray((rng.rand(H // 3 + 1, W // 3 + 1) * 255).astype(np.uint8))
                        .resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    sponge = np.clip(0.45 + 1.1 * sponge, 0, 1)
    out = np.ones((H, W, 3), np.float32)
    for p, ink in enumerate(P.inks):
        cov = np.zeros((H, W), np.float32)
        for tid, t in TOOLS.items():
            layer = Image.new("L", (W, H), 0)
            draw = ImageDraw.Draw(layer)
            for m in (m for m in marks if m["plate"] == p and m["tool"] == tid):
                if t["mode"] == "dab":
                    rings = outline(m)
                    draw.polygon([tuple(v) for v in rings[0] * PX_PER_MM], fill=255)
                    if len(rings) > 1:
                        draw.polygon([tuple(v) for v in rings[1] * PX_PER_MM], fill=0)
                else:
                    wpx = max(1, round(t["width"] * PX_PER_MM))
                    pts = [tuple(np.array(v) * PX_PER_MM) for v in m["pts"]]
                    draw.line(pts, fill=255, width=wpx, joint="curve")
                    for x, y in (pts[0], pts[-1]):
                        draw.ellipse([x - wpx / 2, y - wpx / 2, x + wpx / 2, y + wpx / 2], fill=255)
            c = np.asarray(layer, np.float32) / 255 * t["density"] * (sponge if t.get("texture") else 1)
            cov = 1 - (1 - cov) * (1 - c)
        color = np.array(ink["rgb"], np.float32) / 255
        out = out * (1 - cov[..., None]) + color * cov[..., None]
    return np.clip(out, 0, 1)


def blurred_rmse(img, ref, sigma_px=3):
    b = lambda a: np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize(ref.shape[1::-1], Image.BILINEAR)
                             .filter(ImageFilter.GaussianBlur(sigma_px)), np.float32) / 255
    return float(np.sqrt(((b(img) - b(ref)) ** 2).mean()))


def tool_sheet(path, px=12):
    """One image of the placeholder tool library, true relative size."""
    W, H = 128 * px, 22 * px
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    for i, (tid, t) in enumerate(TOOLS.items()):
        x0 = (8 + i * 18) * px
        if t["mode"] == "dab":
            m = dab(0, tid, 8 + i * 18, 9, 0)
            rings = outline(m)
            d.polygon([tuple(v) for v in rings[0] * px], fill=int(255 * (1 - t["density"])))
            if len(rings) > 1:
                d.polygon([tuple(v) for v in rings[1] * px], fill=255)
        else:
            d.line([(x0 - 4 * px, 5 * px), (x0 + 4 * px, 14 * px)], fill=int(255 * (1 - t["density"])), width=round(t["width"] * px))
        d.text((x0 - 5 * px, 19 * px), f'{tid} ({t["mode"]})', fill=0)
    im.save(path)


def main():
    P = Plates()
    tool_sheet(HERE / "tools.png")
    ref = np.ones(P.a.shape[1:] + (3,), np.float32)
    for a, ink in zip(P.a, P.inks):  # legacy render_alpha_stack, inlined: the JAX composite
        ref = ref * (1 - a[..., None]) + np.array(ink["rgb"], np.float32) / 255 * a[..., None]
    Image.fromarray((ref * 255).astype(np.uint8)).save(HERE / "jax-composite.png")
    legacy = np.asarray(Image.open(ALPHA.parent / "final-svg.png").convert("RGB"), np.float32) / 255
    report = {"legacy-coverage-svg": {"blurred_rmse_vs_jax": round(blurred_rmse(legacy, ref), 4), "marks": 64754}}
    for name, recipe in VARIANTS.items():
        marks = sequence(recipe(P))
        write_svg(P, name, marks, HERE / f"{name}.svg")
        img = preview(P, marks)
        Image.fromarray((img * 255).astype(np.uint8)).save(HERE / f"{name}.png")
        drag_mm = sum(length(m["pts"]) for m in marks if "pts" in m)
        report[name] = {
            "marks": len(marks),
            "dips": len({(m["plate"], m["tool"], m["dip"]) for m in marks}),
            "drag_m": round(drag_mm / 1000, 1),
            "marks_per_tool": dict(sorted(Counter(m["tool"] for m in marks).items())),
            "blurred_rmse_vs_jax": round(blurred_rmse(img, ref), 4),
        }
        print(name, report[name])
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
