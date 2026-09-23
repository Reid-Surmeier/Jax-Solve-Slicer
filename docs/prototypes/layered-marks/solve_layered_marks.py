"""PROTOTYPE, throwaway: JAX solves grid-locked stamps plus dragged wash strokes against an image.

1. The pencil grid is measured from the reference (period and phase) and kept.
2. Underlayer: a wash brush is *dragged*. Per ink and grid cell JAX may lay one stroke (angle, length,
   offset). All drags of one ink merge into a single wet wash at one dilution per ink: overlapping
   strokes of the same colour unify instead of darkening.
3. Stamps: five square-based tools, fixed size, rotatable, locked to Close's diamond lattice (cell
   centres and grid crossings, tiny wobble only). Per ink and lattice point: one tool or none,
   dilution and rotation.
Print order is fixed: warm and light inks first, darker next, black and cold tones last; within an
ink the brush drags go before the stamps. Composite is the legacy over-model, one ink at a time.
Tools are digital PLACEHOLDERS. The darker watercolour rim is a preview of pooling, not toolpath.

Run on the GPU (project .venv has jax[cuda12]==0.10.0):
  .venv/bin/python solve_layered_marks.py close-reference.png
"""
import json
import sys
from functools import partial
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
INKS = json.loads((HERE.parents[1] / "reproduction/2026-09-20/alpha/metadata.json").read_text())["inkset"]["inks"]
G = 32               # solve px per pencil-grid cell
H2 = G // 2          # stamp lattice stride: half a cell (centres + crossings, parity-masked)
GRID_MM = 12.0       # physical grid cell for the SVG
STRENGTHS = (0.25, 0.5, 0.85)  # light wash / medium / full ink cups
STEPS, SEED = 1500, 0
STAMP_COST, BRUSH_COST = 0.0015, 0.0005

# Stamps, in grid-cell units: half width, half height, corner radius. All rotate freely.
STAMPS = {
    "square-L": (0.42, 0.42, 0.10),
    "square-M": (0.30, 0.30, 0.07),
    "square-S": (0.20, 0.20, 0.05),
    "slab": (0.40, 0.20, 0.06),
    "chip": (0.10, 0.10, 0.02),
}
BRUSH = {"name": "wash-brush", "width": 1.2, "min_len": 0.8, "max_len": 3.5}  # grid units
PER_DIP = {"square-L": 7, "square-M": 9, "square-S": 12, "slab": 8, "chip": 16, "wash-brush": 3}
NAMES = list(STAMPS)
GEOM = jnp.asarray([STAMPS[t] for t in NAMES]) * G
S_REACH, B_REACH = 2, 3  # patch reach: stamps in half cells, brush in cells


def lum(rgb):
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cold(rgb):
    return rgb[2] > rgb[0] or lum(rgb) < 0.08


ORDER = sorted(range(len(INKS)), key=lambda i: (cold(INKS[i]["rgb"]), -lum(INKS[i]["rgb"])))
INK_RGB = jnp.asarray([np.array(INKS[i]["rgb"]) / 255 for i in ORDER], jnp.float32)
I, T, S = len(ORDER), len(NAMES), len(STRENGTHS)


def coords(reach, stride):
    p = (2 * reach + 1) * stride
    u = jnp.arange(p) - p / 2 + 0.5
    return jnp.meshgrid(u, u, indexing="ij")  # (y, x) relative to the lattice point


SPY, SPX = coords(S_REACH, H2)
BPY, BPX = coords(B_REACH, G)


# ---- grid: measured from the reference's pencil lines ----
def detect_grid(gray):
    im = Image.fromarray(gray.astype(np.uint8))
    hp = np.asarray(im.filter(ImageFilter.BoxBlur(6)), np.float32) - gray  # thin dark lines -> positive
    out = []
    for axis in (0, 1):  # x from column profile, y from row profile
        prof = hp.clip(0).mean(axis)
        prof = prof - prof.mean()
        freqs = np.fft.rfftfreq(len(prof))[1:]
        spec = np.abs(np.fft.rfft(prof))[1:]
        rough = 1 / freqs[np.argmax(np.where((freqs > 1 / 140) & (freqs < 1 / 40), spec, 0))]
        best = (-1e9, 0, 0)
        for p in np.arange(rough - 4, rough + 4, 0.05):  # refine period and phase with a comb
            for ph in np.arange(0, p, 0.5):
                idx = np.round(np.arange(ph, len(prof), p)).astype(int)
                sc = prof[idx[idx < len(prof)]].mean()
                if sc > best[0]:
                    best = (sc, p, ph)
        out.append(best[1:])
    return out  # [(period_x, phase_x), (period_y, phase_y)]


def load_target(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((32, 32, w - 32, h - 32))  # drop the screenshot's rounded frame
    (px, fx), (py, fy) = detect_grid(np.asarray(im.convert("L"), np.float32))
    nx, ny = int((im.width - fx) // px), int((im.height - fy) // py)
    im = im.crop((round(fx), round(fy), round(fx + nx * px), round(fy + ny * py)))
    grid = {"period_px": [round(float(px), 2), round(float(py), 2)], "phase_px": [float(fx), float(fy)], "cells": [nx, ny]}
    return np.asarray(im.resize((nx * G, ny * G), Image.LANCZOS), np.float32) / 255, grid


def paper(ny, nx):
    """White paper with the pencil grid, as in the reference (not solved, drawn first)."""
    out = np.ones((ny * G, nx * G, 3), np.float32)
    line = np.array([0.55, 0.55, 0.62], np.float32)
    for k in range(0, nx * G, G):
        out[:, k] = 0.6 * out[:, k] + 0.4 * line
    for k in range(0, ny * G, G):
        out[k] = 0.6 * out[k] + 0.4 * line
    return jnp.asarray(out)


def watercolor(sdf, rim_px):
    body = jax.nn.sigmoid(-sdf / 0.4)
    rim = body * jnp.exp(jnp.minimum(sdf, 0) / rim_px)
    return jnp.clip(0.72 * body + 0.4 * rim, 0, 1)


def stamp_fp(off, ang, geom):
    """(I,NY,NX,P,P) for one stamp tool: rounded-box SDF at each lattice point."""
    c, s = jnp.cos(ang)[..., None, None], jnp.sin(ang)[..., None, None]
    # lattice point (r, c) sits exactly at (r*H2, c*H2): half a stride before its patch centre
    px, py = SPX + H2 / 2 - off[..., 0, None, None], SPY + H2 / 2 - off[..., 1, None, None]
    qx, qy = c * px + s * py, -s * px + c * py
    hw, hh, r = geom
    dx, dy = jnp.abs(qx) - (hw - r), jnp.abs(qy) - (hh - r)
    sdf = jnp.sqrt(jnp.maximum(dx, 0) ** 2 + jnp.maximum(dy, 0) ** 2 + 1e-6) + jnp.minimum(jnp.maximum(dx, dy), 0) - r
    return watercolor(sdf, 0.08 * G)


def brush_fp(off, ang, length):
    """(I,NY,NX,P,P): shape of a round wash brush dragged along a segment (1 inside, 0 outside)."""
    c, s = jnp.cos(ang)[..., None, None], jnp.sin(ang)[..., None, None]
    px, py = BPX - off[..., 0, None, None], BPY - off[..., 1, None, None]
    along, across = c * px + s * py, -s * px + c * py
    half = length[..., None, None] / 2
    t = jnp.clip(along, -half, half)
    sdf = jnp.sqrt((along - t) ** 2 + across ** 2 + 1e-6) - BRUSH["width"] * G / 2
    return jax.nn.sigmoid(-sdf / 0.4)


def overlap_add(patches, stride, reach):
    """(I,NY,NX,P,P) patches centred on lattice points of the given stride -> (I,H,W)."""
    i, ny, nx = patches.shape[:3]
    k = 2 * reach + 1
    blocks = patches.reshape(i, ny, nx, k, stride, k, stride)
    canvas = jnp.zeros((i, ny + 2 * reach, nx + 2 * reach, stride, stride))
    for dy in range(k):
        for dx in range(k):
            canvas = canvas.at[:, dy:dy + ny, dx:dx + nx].add(blocks[:, :, :, dy, :, dx, :])
    canvas = canvas[:, reach:reach + ny, reach:reach + nx]
    return canvas.transpose(0, 1, 3, 2, 4).reshape(i, ny * stride, nx * stride)


def lattice_mask(ny2, nx2):
    """Stamp lattice at half-cell stride, keeping only cell centres and grid crossings."""
    yy, xx = np.meshgrid(np.arange(ny2), np.arange(nx2), indexing="ij")
    centre = (yy % 2 == 1) & (xx % 2 == 1)
    crossing = (yy % 2 == 0) & (xx % 2 == 0) & (yy > 0) & (xx > 0)
    return jnp.asarray(centre | crossing)


def ink_logt(sp, so, sa, bp, bo, ba, bl, bs):
    """Log transmittance per ink from stamps and brush drags: (I,H,W)."""
    choice = sp[..., :-1].reshape(sp.shape[:3] + (T, S))

    @partial(jax.checkpoint, static_argnums=(0,))
    def one(t):
        fp = stamp_fp(so, sa, GEOM[t])
        return sum(choice[..., t, k, None, None] * jnp.log1p(-STRENGTHS[k] * fp * 0.999) for k in range(S))

    stamps = overlap_add(sum(one(t) for t in range(T)), H2, S_REACH)
    bfp = jax.checkpoint(brush_fp)(bo, ba, bl)
    union = 1 - jnp.exp(overlap_add(bp[..., None, None] * jnp.log1p(-bfp * 0.999), G, B_REACH))  # merged wash shape
    brush = jnp.log1p(-bs[:, None, None] * union * 0.999)                   # one dilution per ink: overlaps unify
    return stamps + brush


def composite(logt, base, upto=None):
    alpha = 1 - jnp.exp(logt)
    out = base
    for i in range(I if upto is None else upto):
        out = out * (1 - alpha[i, ..., None]) + INK_RGB[i] * alpha[i, ..., None]
    return out


def blur(img, sigma=G / 2):
    r = int(2 * sigma)
    k = jnp.exp(-0.5 * (jnp.arange(-r, r + 1) / sigma) ** 2)
    k = k / k.sum()
    x = jnp.pad(img.transpose(2, 0, 1)[:, None], ((0, 0), (0, 0), (r, r), (r, r)), mode="edge")
    dn = ("NCHW", "OIHW", "NCHW")
    x = jax.lax.conv_general_dilated(x, k[None, None, :, None], (1, 1), "VALID", dimension_numbers=dn)
    x = jax.lax.conv_general_dilated(x, k[None, None, None, :], (1, 1), "VALID", dimension_numbers=dn)
    return x[:, 0].transpose(1, 2, 0)


def geometry(params):
    """Raw params -> bounded, physically meaningful values."""
    s_lg, s_u, s_ang, b_lg, b_u, b_ang, b_len, b_str = params
    s_off = 0.08 * G * jnp.tanh(s_u)                   # stamps: tiny wobble, the lattice is kept
    b_off = 0.35 * G * jnp.tanh(b_u)
    b_len = G * (BRUSH["min_len"] + (BRUSH["max_len"] - BRUSH["min_len"]) * jax.nn.sigmoid(b_len))
    return s_lg, s_off, s_ang, b_lg, b_off, b_ang, b_len, b_str


def straight_through(lg, key, noise, mask=None):
    z = lg + noise * jax.random.gumbel(key, lg.shape)
    if mask is not None:  # forbidden lattice points can only choose "none"
        z = jnp.where(mask[None, :, :, None], z, jnp.full_like(z, -1e9).at[..., -1].set(0.0))
    soft = jax.nn.softmax(z / 0.5, -1)
    return jax.nn.one_hot(jnp.argmax(z, -1), lg.shape[-1]) + soft - jax.lax.stop_gradient(soft)


def solve(target):
    ny, nx = target.shape[0] // G, target.shape[1] // G
    mask = lattice_mask(2 * ny, 2 * nx)
    base = paper(ny, nx)
    tgt, tgt_b = jnp.asarray(target), blur(jnp.asarray(target))
    ks = jax.random.split(jax.random.PRNGKey(SEED), 4)
    params = (0.01 * jax.random.normal(ks[0], (I, 2 * ny, 2 * nx, T * S + 1)).at[..., -1].set(1.0),
              jnp.zeros((I, 2 * ny, 2 * nx, 2)),
              jax.random.uniform(ks[1], (I, 2 * ny, 2 * nx), maxval=jnp.pi / 2),
              0.01 * jax.random.normal(ks[2], (I, ny, nx, 2)).at[..., -1].set(1.0),
              jnp.zeros((I, ny, nx, 2)),
              jax.random.uniform(ks[3], (I, ny, nx), maxval=jnp.pi),
              jnp.zeros((I, ny, nx)),
              jnp.zeros((I, S)))

    def loss(params, key, noise):
        s_lg, s_off, s_ang, b_lg, b_off, b_ang, b_len, b_str = geometry(params)
        k1, k2, k3 = jax.random.split(key, 3)
        sp = straight_through(s_lg, k1, noise, mask)
        bp = straight_through(b_lg, k2, noise)
        bs = straight_through(b_str, k3, noise) @ jnp.asarray(STRENGTHS)  # one wash dilution per ink
        img = composite(ink_logt(sp, s_off, s_ang, bp[..., 0], b_off, b_ang, b_len, bs), base)
        fit = jnp.mean((img - tgt) ** 2) + jnp.mean((blur(img) - tgt_b) ** 2)
        return fit + STAMP_COST * jnp.mean(1 - sp[..., -1]) * I + BRUSH_COST * jnp.mean(1 - bp[..., -1]) * I

    grad = jax.jit(jax.value_and_grad(loss))
    score = jax.jit(loss)
    best = (float("inf"), params)
    m = jax.tree_util.tree_map(jnp.zeros_like, params)
    v = jax.tree_util.tree_map(jnp.zeros_like, params)
    lrs = (0.05, 0.05, 0.03, 0.05, 0.05, 0.03, 0.05, 0.05)
    for step in range(STEPS):  # hand-written Adam, as in the legacy solve
        noise = float(0.6 * (0.02 / 0.6) ** (step / (STEPS - 1)))
        val, g = grad(params, jax.random.PRNGKey(10_000 + step), noise)
        m = jax.tree_util.tree_map(lambda a, b: 0.9 * a + 0.1 * b, m, g)
        v = jax.tree_util.tree_map(lambda a, b: 0.999 * a + 0.001 * b * b, v, g)
        params = tuple(p - lr * (mm / (1 - 0.9 ** (step + 1))) / (jnp.sqrt(vv / (1 - 0.999 ** (step + 1))) + 1e-8)
                       for p, mm, vv, lr in zip(params, m, v, lrs))
        if step % 50 == 0 or step == STEPS - 1:  # keep the best noise-free set of real marks
            clean = float(score(params, jax.random.PRNGKey(0), 0.0))
            if clean < best[0]:
                best = (clean, params)
        if step % 250 == 0 or step == STEPS - 1:
            print(f"step {step} noise {noise:.3f} loss {float(val):.5f} best {best[0]:.5f}", flush=True)
    s_lg, s_off, s_ang, b_lg, b_off, b_ang, b_len, b_str = geometry(best[1])
    s_choice = jnp.where(mask[None], jnp.argmax(s_lg, -1), T * S)
    return dict(s_choice=np.asarray(s_choice), s_off=np.asarray(s_off), s_ang=np.asarray(s_ang),
                b_choice=np.asarray(jnp.argmax(b_lg, -1)), b_off=np.asarray(b_off), b_ang=np.asarray(b_ang),
                b_len=np.asarray(b_len), b_str=np.asarray(jnp.asarray(STRENGTHS)[jnp.argmax(b_str, -1)]), base=base)


def render_hard(sol, upto=None):
    sp = jax.nn.one_hot(jnp.asarray(sol["s_choice"]), T * S + 1)
    bp = (jnp.asarray(sol["b_choice"]) == 0).astype(jnp.float32)
    logt = ink_logt(sp, jnp.asarray(sol["s_off"]), jnp.asarray(sol["s_ang"]), bp,
                    jnp.asarray(sol["b_off"]), jnp.asarray(sol["b_ang"]), jnp.asarray(sol["b_len"]), jnp.asarray(sol["b_str"]))
    return composite(logt, sol["base"], upto)


def marks_from(sol):
    """Toolpath records in print order; within an ink: brush drags, then stamps by tool, serpentine rows."""
    mm = GRID_MM / G
    marks, dip, seq = [], 0, 0
    for k, i in enumerate(ORDER):
        jobs = [("wash-brush", None)] + [(t, n) for n, t in enumerate(NAMES)]
        for tool, t_idx in jobs:
            used = PER_DIP[tool]
            brush = t_idx is None
            ch = sol["b_choice"][k] if brush else sol["s_choice"][k]
            for row in range(ch.shape[0]):
                cols = range(ch.shape[1]) if row % 2 == 0 else reversed(range(ch.shape[1]))
                for col in cols:
                    o = ch[row, col]
                    if (brush and o == 1) or (not brush and (o == T * S or o // S != t_idx)):
                        continue
                    if used >= PER_DIP[tool]:
                        dip, used = dip + 1, 0
                    used += 1
                    if brush:
                        cx = (col + 0.5) * G + sol["b_off"][k, row, col, 0]
                        cy = (row + 0.5) * G + sol["b_off"][k, row, col, 1]
                        a, half = sol["b_ang"][k, row, col], sol["b_len"][k, row, col] / 2
                        ends = [(cx - half * np.cos(a), cy - half * np.sin(a)), (cx + half * np.cos(a), cy + half * np.sin(a))]
                        rec = dict(mode="drag", path=[(float(x * mm), float(y * mm)) for x, y in ends], strength=float(sol["b_str"][k]))
                    else:  # lattice point (row, col) at (col*H2, row*H2): odd = cell centre, even = crossing
                        x = col * H2 + sol["s_off"][k, row, col, 0]
                        y = row * H2 + sol["s_off"][k, row, col, 1]
                        rec = dict(mode="dab", x=float(x * mm), y=float(y * mm), strength=STRENGTHS[o % S],
                                   angle=float(np.degrees(sol["s_ang"][k, row, col]) % 90))
                    marks.append(dict(rec, order=k, ink=i, tool=tool, dip=dip, seq=seq))
                    seq += 1
    return marks


def write_svg(marks, ny, nx, path):
    W, H = nx * GRID_MM, ny * GRID_MM
    f = lambda v: f"{v:.2f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}mm" height="{f(H)}mm" viewBox="0 0 {f(W)} {f(H)}">',
           "<metadata>" + json.dumps({"prototype": "jax grid stamps + brush drags", "tools": "PLACEHOLDER digital footprints",
                                      "print_order": [INKS[i]["label"] for i in ORDER],
                                      "wash": "brush drags of one ink share a group opacity, so overlaps unify"}) + "</metadata>",
           '<rect width="100%" height="100%" fill="#fff"/>', "<defs>"]
    for t, (hw, hh, r) in STAMPS.items():
        out.append(f'<rect id="tool-{t}" x="{f(-hw * GRID_MM)}" y="{f(-hh * GRID_MM)}" width="{f(2 * hw * GRID_MM)}" '
                   f'height="{f(2 * hh * GRID_MM)}" rx="{f(r * GRID_MM)}" fill="currentColor"/>')
    out.append("</defs>")
    out.append('<g id="00-pencil-grid" stroke="#8c8c9e" stroke-width="0.15" fill="none">'
               + "".join(f'<path d="M {f(x * GRID_MM)},0 V {f(H)}"/>' for x in range(nx + 1))
               + "".join(f'<path d="M 0,{f(y * GRID_MM)} H {f(W)}"/>' for y in range(ny + 1)) + "</g>")
    for k, i in enumerate(ORDER):
        ink = INKS[i]
        col = "#" + "".join(f"{c:02x}" for c in ink["rgb"])
        out.append(f'<g id="print-{k + 1:02d}-{ink["role"]}" data-ink="{ink["id"]}" data-print-order="{k + 1}" color="{col}">')
        drags = [m for m in marks if m["order"] == k and m["mode"] == "drag"]
        if drags:  # one wet wash: strokes at full strength inside, the ink's dilution on the group
            out.append(f'<g data-tool="wash-brush" data-strength="{drags[0]["strength"]}" opacity="{drags[0]["strength"]}">')
            for m in drags:
                (x0, y0), (x1, y1) = m["path"]
                out.append(f'<path d="M {f(x0)},{f(y0)} L {f(x1)},{f(y1)}" stroke="{col}" stroke-width="{f(BRUSH["width"] * GRID_MM)}" '
                           f'stroke-linecap="round" fill="none" data-mode="drag" data-dip="{m["dip"]}" data-seq="{m["seq"]}"/>')
            out.append("</g>")
        for m in (m for m in marks if m["order"] == k and m["mode"] == "dab"):
            data = f'data-tool="{m["tool"]}" data-mode="{m["mode"]}" data-strength="{m["strength"]}" data-dip="{m["dip"]}" data-seq="{m["seq"]}"'
            out.append(f'<use href="#tool-{m["tool"]}" transform="translate({f(m["x"])} {f(m["y"])}) rotate({m["angle"]:.1f})" '
                           f'opacity="{m["strength"]}" {data}/>')
        out.append("</g>")
    out.append("</svg>")
    path.write_text("\n".join(out))


def to_png(img, path):
    Image.fromarray((np.clip(np.asarray(img), 0, 1) * 255).astype(np.uint8)).save(path)


def main():
    target, grid = load_target(sys.argv[1])
    ny, nx = target.shape[0] // G, target.shape[1] // G
    to_png(target, HERE / "target.png")
    sol = solve(target)
    final = render_hard(sol)
    to_png(final, HERE / "jax-marks.png")
    frames = [Image.fromarray((np.asarray(render_hard(sol, upto=k + 1)) * 255).astype(np.uint8)) for k in range(I)]
    frames[0].save(HERE / "print-order.gif", save_all=True, append_images=frames[1:] + [frames[-1]] * 3, duration=700, loop=0)
    strip = Image.new("RGB", (frames[0].width * 6, frames[0].height * 2), "white")
    for k, fr in enumerate(frames):
        strip.paste(fr, ((k % 6) * fr.width, (k // 6) * fr.height))
    strip.save(HERE / "print-order-strip.png")
    marks = marks_from(sol)
    write_svg(marks, ny, nx, HERE / "layered-marks.svg")
    report = {
        "grid": grid,
        "rmse": round(float(jnp.sqrt(jnp.mean((final - target) ** 2))), 4),
        "blurred_rmse": round(float(jnp.sqrt(jnp.mean((blur(final) - blur(jnp.asarray(target))) ** 2))), 4),
        "marks": len(marks), "dips": len({m["dip"] for m in marks}),
        "drags": sum(m["mode"] == "drag" for m in marks),
        "drag_mm": round(sum(float(np.hypot(*np.subtract(*m["path"]))) for m in marks if m["mode"] == "drag"), 1),
        "marks_per_tool": {t: sum(m["tool"] == t for m in marks) for t in ["wash-brush"] + NAMES},
        "print_order": [{"ink": INKS[i]["label"], "marks": sum(m["ink"] == i for m in marks)} for i in ORDER],
        "jax": jax.__version__, "backend": jax.default_backend(), "steps": STEPS,
    }
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("grid", "rmse", "blurred_rmse", "marks", "drags", "dips", "marks_per_tool")}))


if __name__ == "__main__":
    main()
