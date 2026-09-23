"""PROTOTYPE, throwaway: JAX solves layered tool marks directly against an image.

The question: can JAX choose, for every grid cell and every ink, which fixed tool mark (or none) and
which dilution to print, so that the *overlaps* of transparent marks make the image's mixtures?
Print order is fixed: warm/light inks first, darker next, black and cold tones last. The composite is
the legacy over-model (plate_solver/overprint.py), applied mark layer by mark layer in that order.
Tools are digital PLACEHOLDERS (fixed shapes, never scaled); dilutions stand in for ink cups.

Run with a Python that has jax==0.10.0 (the version in the 2026-09-20 receipt):
  python solve_layered_marks.py target.png
"""
import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
INKS = json.loads((HERE.parents[1] / "reproduction/2026-09-20/alpha/metadata.json").read_text())["inkset"]["inks"]
CELL = 16            # solve raster px per grid cell
KS = 31              # tool kernel px; marks can spill about one cell into neighbours
NX = 20              # grid columns (the reference drawing has about 20)
CELL_MM = 12.0       # physical cell size for the SVG
STRENGTHS = (0.3, 0.6, 0.9)  # light wash / medium / full ink cups
STEPS, SPARSITY, SEED = 1200, 0.002, 0

# ---- tools: fixed footprints in cell units, rasterised once ----
TOOL_SHAPES = {
    "sponge-L": ("blob", 0.62), "sponge-M": ("blob", 0.42), "ring": ("ring", (0.46, 0.25)),
    "diamond": ("diamond", 0.55), "square": ("square", 0.30), "dot": ("dot", 0.17),
}
PER_DIP = {"sponge-L": 6, "sponge-M": 8, "ring": 8, "diamond": 8, "square": 10, "dot": 14}


def tool_outline(kind, size, n=40):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if kind == "blob":
        wob = 1 + 0.12 * np.sin(3 * t + 1) + 0.07 * np.sin(5 * t)
        return [np.c_[np.cos(t), np.sin(t)] * size * wob[:, None]]
    if kind == "ring":
        return [np.c_[np.cos(t), np.sin(t)] * size[0], np.c_[np.cos(t), np.sin(t)] * size[1]]
    if kind == "dot":
        return [np.c_[np.cos(t), np.sin(t)] * size]
    s = size
    sq = np.array([[-s, -s], [s, -s], [s, s], [-s, s]])
    return [sq @ np.array([[0.7071, -0.7071], [0.7071, 0.7071]]) if kind == "diamond" else sq]


def tool_kernel(rings, ss=4):
    big = KS * ss
    im = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(im)
    for k, ring in enumerate(rings):
        d.polygon([tuple(v) for v in ring * CELL * ss + big / 2], fill=0 if k else 255)
    return np.asarray(im.resize((KS, KS), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255


TOOLS = list(TOOL_SHAPES)
OUTLINES = {t: tool_outline(*TOOL_SHAPES[t]) for t in TOOLS}
KERNELS = jnp.asarray(np.stack([tool_kernel(OUTLINES[t]) for t in TOOLS])[:, None])  # (T,1,KS,KS)


# ---- print order: warm/light first, darker next, black and cold tones last ----
def lum(rgb):
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cold(rgb):
    return rgb[2] > rgb[0] or lum(rgb) < 0.08


ORDER = sorted(range(len(INKS)), key=lambda i: (cold(INKS[i]["rgb"]), -lum(INKS[i]["rgb"])))
INK_RGB = jnp.asarray([np.array(INKS[i]["rgb"]) / 255 for i in ORDER], jnp.float32)  # print order
I, T, S = len(ORDER), len(TOOLS), len(STRENGTHS)
LOG_KEEP = jnp.log1p(-jnp.asarray(STRENGTHS))  # per-strength log transmittance of a full-cover mark


def load_target(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((32, 32, w - 32, h - 32))  # drop the screenshot's rounded frame
    ny = round(NX * im.size[1] / im.size[0])
    return np.asarray(im.resize((NX * CELL, ny * CELL), Image.LANCZOS), np.float32) / 255


def render(probs, upto=None):
    """probs (I,NY,NX,T*S+1) in print order -> RGB (H,W,3); per-ink coverage then legacy over-model."""
    marks = probs[..., :-1].reshape(probs.shape[:3] + (T, S))
    depth = (marks * LOG_KEEP).sum(-1)                        # (I,NY,NX,T) log transmittance at centre
    ny, nx = depth.shape[1:3]
    grid = jnp.zeros((I, T, ny * CELL, nx * CELL)).at[:, :, CELL // 2::CELL, CELL // 2::CELL].set(depth.transpose(0, 3, 1, 2))
    spread = jax.lax.conv_general_dilated(grid, KERNELS, (1, 1), "SAME", feature_group_count=T,
                                          dimension_numbers=("NCHW", "OIHW", "NCHW"))
    alpha = 1 - jnp.exp(spread.sum(1))                        # (I,H,W) coverage of each ink
    out = jnp.ones(alpha.shape[1:] + (3,))
    for i in range(I if upto is None else upto):
        out = out * (1 - alpha[i, ..., None]) + INK_RGB[i] * alpha[i, ..., None]
    return out


def blur(img, sigma=CELL / 2):
    r = int(2 * sigma)
    k = jnp.exp(-0.5 * (jnp.arange(-r, r + 1) / sigma) ** 2)
    k = k / k.sum()
    x = jnp.pad(img.transpose(2, 0, 1)[:, None], ((0, 0), (0, 0), (r, r), (r, r)), mode="edge")
    dn = ("NCHW", "OIHW", "NCHW")
    x = jax.lax.conv_general_dilated(x, k[None, None, :, None], (1, 1), "VALID", dimension_numbers=dn)
    x = jax.lax.conv_general_dilated(x, k[None, None, None, :], (1, 1), "VALID", dimension_numbers=dn)
    return x[:, 0].transpose(1, 2, 0)


def solve(target):
    ny = target.shape[0] // CELL
    tgt, tgt_b = jnp.asarray(target), blur(jnp.asarray(target))
    key = jax.random.PRNGKey(SEED)
    logits = 0.01 * jax.random.normal(key, (I, ny, NX, T * S + 1))
    logits = logits.at[..., -1].set(1.0)  # start mostly empty

    def loss(lg, tau, hard):
        p = jax.nn.softmax(lg / tau, -1)
        # second half: straight-through, the render sees the real (one tool or none) choice
        p = jnp.where(hard, jax.nn.one_hot(jnp.argmax(lg, -1), p.shape[-1]) + p - jax.lax.stop_gradient(p), p)
        img = render(p)
        fit = jnp.mean((img - tgt) ** 2) + 2.0 * jnp.mean((blur(img) - tgt_b) ** 2)
        return fit + SPARSITY * jnp.mean(1 - p[..., -1]) * I

    grad = jax.jit(jax.value_and_grad(loss))
    half = STEPS // 2
    m = v = jnp.zeros_like(logits)
    for step in range(STEPS):  # hand-written Adam, as in the legacy solve
        tau = float(0.12 ** (min(step, half) / half))
        val, g = grad(logits, tau, step >= half)
        m, v = 0.9 * m + 0.1 * g, 0.999 * v + 0.001 * g * g
        logits = logits - 0.08 * (m / (1 - 0.9 ** (step + 1))) / (jnp.sqrt(v / (1 - 0.999 ** (step + 1))) + 1e-8)
        if step % 150 == 0 or step == STEPS - 1:
            print(f"step {step} tau {tau:.3f} loss {float(val):.5f}", flush=True)
    return np.asarray(jnp.argmax(logits, -1))  # hard choice per ink per cell


def marks_from_choice(choice):
    marks, dip, seq = [], 0, 0
    for k, i in enumerate(ORDER):             # print order
        for t_idx, tool in enumerate(TOOLS):  # one tool at a time per ink
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
                    marks.append(dict(order=k, ink=i, tool=tool, strength=STRENGTHS[o % S], row=row, col=col, dip=dip, seq=seq))
                    seq += 1
            # a new ink or tool always needs a fresh dip
    return marks


def hard_probs(choice):
    return jax.nn.one_hot(jnp.asarray(choice), T * S + 1)


def write_svg(marks, ny, path):
    W, H = NX * CELL_MM, ny * CELL_MM
    f = lambda v: f"{v:.2f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W)}mm" height="{f(H)}mm" viewBox="0 0 {f(W)} {f(H)}">',
           "<metadata>" + json.dumps({"prototype": "jax layered marks", "tools": "PLACEHOLDER digital footprints",
                                      "print_order": [INKS[i]["label"] for i in ORDER]}) + "</metadata>",
           '<rect width="100%" height="100%" fill="#fff"/>', "<defs>"]
    for t in TOOLS:
        d = " ".join("M " + " L ".join(f"{f(x * CELL_MM)},{f(y * CELL_MM)}" for x, y in r) + " Z" for r in OUTLINES[t])
        out.append(f'<symbol id="tool-{t}" overflow="visible"><path d="{d}" fill="currentColor" fill-rule="evenodd"/></symbol>')
    out.append("</defs>")
    for k, i in enumerate(ORDER):
        ink = INKS[i]
        col = "#" + "".join(f"{c:02x}" for c in ink["rgb"])
        out.append(f'<g id="print-{k + 1:02d}-{ink["role"]}" data-ink="{ink["id"]}" data-print-order="{k + 1}" color="{col}">')
        for m in (m for m in marks if m["order"] == k):
            x, y = (m["col"] + 0.5) * CELL_MM, (m["row"] + 0.5) * CELL_MM
            out.append(f'<use href="#tool-{m["tool"]}" x="{f(x)}" y="{f(y)}" opacity="{m["strength"]}" data-tool="{m["tool"]}" '
                       f'data-strength="{m["strength"]}" data-dip="{m["dip"]}" data-seq="{m["seq"]}"/>')
        out.append("</g>")
    out.append("</svg>")
    path.write_text("\n".join(out))


def to_png(img, path, scale=1):
    im = Image.fromarray((np.clip(np.asarray(img), 0, 1) * 255).astype(np.uint8))
    (im.resize((im.width * scale, im.height * scale), Image.NEAREST) if scale > 1 else im).save(path)


def main():
    out = HERE
    target = load_target(sys.argv[1])
    to_png(target, out / "target.png")
    choice = solve(target)
    probs = hard_probs(choice)
    final = render(probs)
    to_png(final, out / "jax-marks.png")
    frames = [Image.fromarray((np.asarray(render(probs, upto=k + 1)) * 255).astype(np.uint8)) for k in range(I)]
    frames[0].save(out / "print-order.gif", save_all=True, append_images=frames[1:] + [frames[-1]] * 3, duration=700, loop=0)
    strip = Image.new("RGB", (frames[0].width * 6, frames[0].height * 2), "white")
    for k, fr in enumerate(frames):
        strip.paste(fr, ((k % 6) * fr.width, (k // 6) * fr.height))
    strip.save(out / "print-order-strip.png")
    marks = marks_from_choice(choice)
    write_svg(marks, choice.shape[1], out / "layered-marks.svg")
    per_cell = (choice != T * S).sum(0)
    report = {
        "rmse": round(float(jnp.sqrt(jnp.mean((final - target) ** 2))), 4),
        "blurred_rmse": round(float(jnp.sqrt(jnp.mean((blur(final) - blur(jnp.asarray(target))) ** 2))), 4),
        "marks": len(marks), "dips": len({m["dip"] for m in marks}),
        "marks_per_cell": {str(n): int((per_cell == n).sum()) for n in range(int(per_cell.max()) + 1)},
        "marks_per_tool": {t: sum(m["tool"] == t for m in marks) for t in TOOLS},
        "marks_per_strength": {str(s): sum(m["strength"] == s for m in marks) for s in STRENGTHS},
        "print_order": [{"ink": INKS[i]["label"], "marks": sum(m["ink"] == i for m in marks)} for i in ORDER],
        "jax": jax.__version__, "backend": jax.default_backend(), "steps": STEPS, "grid": [NX, int(choice.shape[1])],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("rmse", "blurred_rmse", "marks", "dips", "marks_per_cell")}))


if __name__ == "__main__":
    main()
