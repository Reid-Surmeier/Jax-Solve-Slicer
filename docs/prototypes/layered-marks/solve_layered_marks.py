"""PROTOTYPE, throwaway: JAX solves layered, rotated square-tool marks directly against an image.

For every placement cell and every ink, JAX chooses one of 6 fixed square-based tools (or none), a
dilution, an offset inside the cell and a rotation. Transparent marks overlap their neighbours, so
pale washes underneath shine through the darker marks printed later. Print order is fixed: warm and
light inks first, darker next, black and cold tones last (legacy over-model, one ink at a time).
Tools are digital PLACEHOLDERS (fixed size, never scaled). The darker watercolour rim is a preview
of ink pooling, not part of the toolpath.

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
from PIL import Image

HERE = Path(__file__).parent
INKS = json.loads((HERE.parents[1] / "reproduction/2026-09-20/alpha/metadata.json").read_text())["inkset"]["inks"]
CELL = 16            # solve px per placement cell
NX = 30              # placement cells across (about 2 per pencil-grid square of the reference)
REACH = 2            # a mark may cover this many cells either side of its own
CELL_MM = 7.0        # physical placement pitch for the SVG
STRENGTHS = (0.25, 0.5, 0.85)  # light wash / medium / full ink cups
STEPS, SPARSITY, SEED = 1500, 0.0015, 0

# Six square-based tools, in cell units: half width, half height, corner radius. All rotate freely.
TOOLS = {
    "wash-XL": (1.00, 1.00, 0.40),   # pale underlayer washes
    "square-L": (0.75, 0.75, 0.22),
    "square-M": (0.52, 0.52, 0.14),
    "square-S": (0.34, 0.34, 0.09),
    "slab": (0.70, 0.36, 0.12),      # rectangular mark
    "chip": (0.18, 0.18, 0.04),      # small dark accents
}
PER_DIP = {"wash-XL": 5, "square-L": 7, "square-M": 9, "square-S": 12, "slab": 8, "chip": 16}
NAMES = list(TOOLS)
GEOM = jnp.asarray([TOOLS[t] for t in NAMES]) * CELL  # (T,3) px


def lum(rgb):
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cold(rgb):
    return rgb[2] > rgb[0] or lum(rgb) < 0.08


ORDER = sorted(range(len(INKS)), key=lambda i: (cold(INKS[i]["rgb"]), -lum(INKS[i]["rgb"])))
INK_RGB = jnp.asarray([np.array(INKS[i]["rgb"]) / 255 for i in ORDER], jnp.float32)
I, T, S = len(ORDER), len(NAMES), len(STRENGTHS)
P = (2 * REACH + 1) * CELL
_u = (jnp.arange(P) - P / 2 + 0.5)
PY, PX = jnp.meshgrid(_u, _u, indexing="ij")  # patch pixel coords relative to the cell centre


def load_target(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((32, 32, w - 32, h - 32))  # drop the screenshot's rounded frame
    ny = round(NX * im.size[1] / im.size[0])
    return np.asarray(im.resize((NX * CELL, ny * CELL), Image.LANCZOS), np.float32) / 255


def footprints(off, ang, geom=GEOM):
    """Soft alpha of every tool for every (ink, cell): (I,NY,NX,T,P,P). Rounded-box SDF, darker rim."""
    c, s = jnp.cos(ang)[..., None, None], jnp.sin(ang)[..., None, None]
    px, py = PX - off[..., 0, None, None], PY - off[..., 1, None, None]
    qx, qy = c * px + s * py, -s * px + c * py
    hw, hh, r = (geom[:, k][:, None, None] for k in range(3))
    dx = jnp.abs(qx[..., None, :, :]) - (hw - r)
    dy = jnp.abs(qy[..., None, :, :]) - (hh - r)
    sdf = jnp.sqrt(jnp.maximum(dx, 0) ** 2 + jnp.maximum(dy, 0) ** 2 + 1e-6) + jnp.minimum(jnp.maximum(dx, dy), 0) - r
    body = jax.nn.sigmoid(-sdf / 0.35)
    rim = body * jnp.exp(jnp.minimum(sdf, 0) / (0.08 * CELL))
    return jnp.clip(0.72 * body + 0.4 * rim, 0, 1)


def overlap_add(patches, ny, nx):
    """(I,NY,NX,P,P) patches centred on their cells -> (I,H,W) canvas."""
    k = 2 * REACH + 1
    blocks = patches.reshape(I, ny, nx, k, CELL, k, CELL)
    canvas = jnp.zeros((I, ny + 2 * REACH, nx + 2 * REACH, CELL, CELL))
    for dy in range(k):
        for dx in range(k):
            canvas = canvas.at[:, dy:dy + ny, dx:dx + nx].add(blocks[:, :, :, dy, :, dx, :])
    canvas = canvas[:, REACH:REACH + ny, REACH:REACH + nx]
    return canvas.transpose(0, 1, 3, 2, 4).reshape(I, ny * CELL, nx * CELL)


def render(probs, off, ang, upto=None):
    ny, nx = probs.shape[1:3]
    choice = probs[..., :-1].reshape(probs.shape[:3] + (T, S))
    # log transmittance: sum over tool/strength options of p * log(1 - strength * footprint), one tool at a time
    @partial(jax.checkpoint, static_argnums=(0,))
    def tool_logt(t):
        fp = footprints(off, ang, GEOM[t:t + 1])[..., 0, :, :]              # (I,NY,NX,P,P)
        return sum(choice[..., t, k, None, None] * jnp.log1p(-STRENGTHS[k] * fp * 0.999) for k in range(S))
    logt = sum(tool_logt(t) for t in range(T))
    alpha = 1 - jnp.exp(overlap_add(logt, ny, nx))                           # (I,H,W)
    out = jnp.ones(alpha.shape[1:] + (3,))
    for i in range(I if upto is None else upto):
        out = out * (1 - alpha[i, ..., None]) + INK_RGB[i] * alpha[i, ..., None]
    return out


def blur(img, sigma=CELL):
    r = int(2 * sigma)
    k = jnp.exp(-0.5 * (jnp.arange(-r, r + 1) / sigma) ** 2)
    k = k / k.sum()
    x = jnp.pad(img.transpose(2, 0, 1)[:, None], ((0, 0), (0, 0), (r, r), (r, r)), mode="edge")
    dn = ("NCHW", "OIHW", "NCHW")
    x = jax.lax.conv_general_dilated(x, k[None, None, :, None], (1, 1), "VALID", dimension_numbers=dn)
    x = jax.lax.conv_general_dilated(x, k[None, None, None, :], (1, 1), "VALID", dimension_numbers=dn)
    return x[:, 0].transpose(1, 2, 0)


def unpack(params):
    lg, u, ang = params
    return lg, 0.5 * CELL * jnp.tanh(u), ang


def solve(target):
    ny = target.shape[0] // CELL
    tgt, tgt_b = jnp.asarray(target), blur(jnp.asarray(target))
    k1, k2, k3 = jax.random.split(jax.random.PRNGKey(SEED), 3)
    params = (0.01 * jax.random.normal(k1, (I, ny, NX, T * S + 1)).at[..., -1].set(1.0),
              jax.random.uniform(k3, (I, ny, NX, 2), minval=-1.2, maxval=1.2),  # off-centre: no nesting
              jax.random.uniform(k2, (I, ny, NX), minval=0, maxval=jnp.pi / 2))

    def loss(params, key, noise):
        lg, off, ang = unpack(params)
        # Gumbel straight-through: the render always sees real marks (one tool or none), noise explores
        z = lg + noise * jax.random.gumbel(key, lg.shape)
        soft = jax.nn.softmax(z / 0.5, -1)
        p = jax.nn.one_hot(jnp.argmax(z, -1), lg.shape[-1]) + soft - jax.lax.stop_gradient(soft)
        img = render(p, off, ang)
        fit = jnp.mean((img - tgt) ** 2) + jnp.mean((blur(img) - tgt_b) ** 2)
        return fit + SPARSITY * jnp.mean(1 - p[..., -1]) * I

    grad = jax.jit(jax.value_and_grad(loss))
    score = jax.jit(loss)
    best = (float("inf"), params)
    m = jax.tree_util.tree_map(jnp.zeros_like, params)
    v = jax.tree_util.tree_map(jnp.zeros_like, params)
    for step in range(STEPS):  # hand-written Adam, as in the legacy solve
        lrs = (0.05, 0.05, 0.03)
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
    lg, off, ang = unpack(best[1])
    return np.asarray(jnp.argmax(lg, -1)), np.asarray(off), np.asarray(ang)


def marks_from(choice, off, ang):
    marks, dip, seq = [], 0, 0
    for k, i in enumerate(ORDER):              # print order
        for t_idx, tool in enumerate(NAMES):   # one tool at a time per ink, fresh dip on change
            used = PER_DIP[tool]
            for row in range(choice.shape[1]):
                cols = range(choice.shape[2]) if row % 2 == 0 else reversed(range(choice.shape[2]))
                for col in cols:
                    o = choice[k, row, col]
                    if o == T * S or o // S != t_idx:
                        continue
                    if used >= PER_DIP[tool]:
                        dip, used = dip + 1, 0
                    used += 1
                    x = (col + 0.5 + off[k, row, col, 0] / CELL) * CELL_MM
                    y = (row + 0.5 + off[k, row, col, 1] / CELL) * CELL_MM
                    marks.append(dict(order=k, ink=i, tool=tool, strength=STRENGTHS[o % S], x=float(x), y=float(y),
                                      angle=float(np.degrees(ang[k, row, col]) % 90), dip=dip, seq=seq))
                    seq += 1
    return marks


def write_svg(marks, ny, path):
    W, H = NX * CELL_MM, ny * CELL_MM
    f = lambda v: f"{v:.2f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}mm" height="{f(H)}mm" viewBox="0 0 {f(W)} {f(H)}">',
           "<metadata>" + json.dumps({"prototype": "jax layered square marks", "tools": "PLACEHOLDER digital footprints",
                                      "print_order": [INKS[i]["label"] for i in ORDER]}) + "</metadata>",
           '<rect width="100%" height="100%" fill="#fff"/>', "<defs>"]
    for t, (hw, hh, r) in TOOLS.items():
        out.append(f'<rect id="tool-{t}" x="{f(-hw * CELL_MM)}" y="{f(-hh * CELL_MM)}" width="{f(2 * hw * CELL_MM)}" '
                   f'height="{f(2 * hh * CELL_MM)}" rx="{f(r * CELL_MM)}" fill="currentColor"/>')
    out.append("</defs>")
    for k, i in enumerate(ORDER):
        ink = INKS[i]
        col = "#" + "".join(f"{c:02x}" for c in ink["rgb"])
        out.append(f'<g id="print-{k + 1:02d}-{ink["role"]}" data-ink="{ink["id"]}" data-print-order="{k + 1}" color="{col}">')
        for m in (m for m in marks if m["order"] == k):
            out.append(f'<use href="#tool-{m["tool"]}" transform="translate({f(m["x"])} {f(m["y"])}) rotate({m["angle"]:.1f})" '
                       f'opacity="{m["strength"]}" data-tool="{m["tool"]}" data-strength="{m["strength"]}" '
                       f'data-dip="{m["dip"]}" data-seq="{m["seq"]}"/>')
        out.append("</g>")
    out.append("</svg>")
    path.write_text("\n".join(out))


def to_png(img, path):
    Image.fromarray((np.clip(np.asarray(img), 0, 1) * 255).astype(np.uint8)).save(path)


def tool_sheet(path, px=40):
    im = Image.new("L", (px * 3 * T, px * 3), 255)
    for n, (hw, hh, r) in enumerate(TOOLS.values()):
        a = np.asarray(footprints(jnp.zeros((1, 1, 1, 2)), jnp.full((1, 1, 1), 0.3), jnp.asarray([[hw, hh, r]]) * CELL))[0, 0, 0, 0]
        tile = Image.fromarray((255 * (1 - 0.85 * a)).astype(np.uint8)).resize((px * 3, px * 3), Image.LANCZOS)
        im.paste(tile, (n * px * 3, 0))
    im.save(path)


def main():
    target = load_target(sys.argv[1])
    to_png(target, HERE / "target.png")
    tool_sheet(HERE / "tools.png")
    choice, off, ang = solve(target)
    probs = jax.nn.one_hot(jnp.asarray(choice), T * S + 1)
    final = render(probs, jnp.asarray(off), jnp.asarray(ang))
    to_png(final, HERE / "jax-marks.png")
    frames = [Image.fromarray((np.asarray(render(probs, jnp.asarray(off), jnp.asarray(ang), upto=k + 1)) * 255).astype(np.uint8))
              for k in range(I)]
    frames[0].save(HERE / "print-order.gif", save_all=True, append_images=frames[1:] + [frames[-1]] * 3, duration=700, loop=0)
    strip = Image.new("RGB", (frames[0].width * 6, frames[0].height * 2), "white")
    for k, fr in enumerate(frames):
        strip.paste(fr, ((k % 6) * fr.width, (k // 6) * fr.height))
    strip.save(HERE / "print-order-strip.png")
    marks = marks_from(choice, off, ang)
    write_svg(marks, choice.shape[1], HERE / "layered-marks.svg")
    per_cell = (choice != T * S).sum(0)
    report = {
        "rmse": round(float(jnp.sqrt(jnp.mean((final - target) ** 2))), 4),
        "blurred_rmse": round(float(jnp.sqrt(jnp.mean((blur(final) - blur(jnp.asarray(target))) ** 2))), 4),
        "marks": len(marks), "dips": len({m["dip"] for m in marks}),
        "marks_per_cell": {str(n): int((per_cell == n).sum()) for n in range(int(per_cell.max()) + 1)},
        "marks_per_tool": {t: sum(m["tool"] == t for m in marks) for t in NAMES},
        "marks_per_strength": {str(s): sum(m["strength"] == s for m in marks) for s in STRENGTHS},
        "print_order": [{"ink": INKS[i]["label"], "marks": sum(m["ink"] == i for m in marks)} for i in ORDER],
        "jax": jax.__version__, "backend": jax.default_backend(), "steps": STEPS, "grid": [NX, int(choice.shape[1])],
    }
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("rmse", "blurred_rmse", "marks", "dips", "marks_per_tool")}))


if __name__ == "__main__":
    main()
