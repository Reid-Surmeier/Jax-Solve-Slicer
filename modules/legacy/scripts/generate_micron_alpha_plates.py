#!/usr/bin/env python
"""Generate fixed-palette high-resolution alpha plates.

This intentionally stops before SVG/vector realization. It solves soft alpha
plates directly against a source image, then writes high-bit-depth PNG masks and
colored previews for physical-pen planning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from plotter_separation.inkset import Ink, InkSet  # noqa: E402
from plotter_separation.overprint import composite_error, render_alpha_stack  # noqa: E402
from plotter_separation.plate_solver import initialize_alpha_stack  # noqa: E402
from plotter_separation.source_prep import auto_crop_artwork  # noqa: E402


MICRON_XSDK05_INKS = (
    Ink("xsdk05_243", "XSDK05#243 blue black", (22, 41, 55), "blue_black"),
    Ink("xsdk05_032", "XSDK05#32 fresh green", (0, 132, 86), "fresh_green"),
    Ink("xsdk05_117", "XSDK05#117 sepia", (94, 61, 39), "sepia"),
    Ink("xsdk05_021", "XSDK05#21 rose", (205, 73, 134), "rose"),
    Ink("xsdk05_003", "XSDK05#3 yellow", (245, 196, 28), "yellow"),
    Ink("xsdk05_024", "XSDK05#24 purple", (95, 59, 132), "purple"),
    Ink("xsdk05_049", "XSDK05#49 black", (16, 15, 14), "black"),
    Ink("xsdk05_005", "XSDK05#5 orange", (232, 105, 35), "orange"),
    Ink("xsdk05_019", "XSDK05#19 red", (198, 39, 33), "red"),
    Ink("xsdk05_022", "XSDK05#22 burgundy", (112, 31, 62), "burgundy"),
    Ink("xsdk05_036", "XSDK05#36 blue", (30, 91, 176), "blue"),
    Ink("xsdk05_138", "XSDK05#138 royal blue", (42, 64, 148), "royal_blue"),
)

AVAILABLE_MICRON_XSDK05_INKS = (
    Ink("xsdk05_021", "XSDK05#21 rose", (205, 73, 134), "rose"),
    Ink("xsdk05_003", "XSDK05#3 yellow", (245, 196, 28), "yellow"),
    Ink("xsdk05_117", "XSDK05#117 sepia", (94, 61, 39), "sepia"),
    Ink("xsdk05_032", "XSDK05#32 fresh green", (0, 132, 86), "fresh_green"),
    Ink("xsdk05_024", "XSDK05#24 purple", (95, 59, 132), "purple"),
    Ink("xsdk05_049", "XSDK05#49 black", (16, 15, 14), "black"),
    Ink("xsdk05_005", "XSDK05#5 orange", (232, 105, 35), "orange"),
    Ink("xsdk05_019", "XSDK05#19 red", (198, 39, 33), "red"),
    Ink("xsdk05_036", "XSDK05#36 blue / light blue", (30, 91, 176), "light_blue"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--target-mode", choices=("layout_right", "full", "crop_artwork"), default="layout_right")
    parser.add_argument("--upscale", choices=("realesrgan", "lanczos", "none"), default="realesrgan")
    parser.add_argument("--upscale-scale", type=int, default=2)
    parser.add_argument("--realesrgan-bin", default="realesrgan-ncnn-vulkan")
    parser.add_argument("--realesrgan-model", default="realesrgan-x4plus")
    parser.add_argument("--steps", type=int, default=700)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--alpha-prior-weight", type=float, default=0.003)
    parser.add_argument("--tile-pixels", type=int, default=65536)
    parser.add_argument("--palette", choices=("full12", "available"), default="full12")
    parser.add_argument("--paper-rgb", default="255,255,255")
    parser.add_argument("--seed", type=int, default=2001)
    args = parser.parse_args()

    out = args.out_dir
    alpha_dir = out / "alpha16"
    alpha8_dir = out / "alpha8"
    preview_dir = out / "plate_previews"
    for directory in (out, alpha_dir, alpha8_dir, preview_dir):
        directory.mkdir(parents=True, exist_ok=True)

    paper_rgb = _parse_rgb(args.paper_rgb)
    inks = AVAILABLE_MICRON_XSDK05_INKS if args.palette == "available" else MICRON_XSDK05_INKS
    inkset = InkSet(inks=inks, paper_rgb=paper_rgb, mode=f"micron_xsdk05_{args.palette}")

    source = Image.open(args.image).convert("RGB")
    target = _select_target(source, args.target_mode)
    target.save(out / "target_crop.png")
    working, source_variant = _upscale_target(
        target,
        out_dir=out / "source_variant",
        method=args.upscale,
        scale=args.upscale_scale,
        realesrgan_bin=args.realesrgan_bin,
        realesrgan_model=args.realesrgan_model,
    )
    working.save(out / "target_upscaled.png")
    target_rgb = np.asarray(working, dtype=np.float32) / 255.0

    seed_result = initialize_alpha_stack(target_rgb, inkset)
    result = solve_alpha_stack_jax(
        target_rgb,
        seed_result.alpha_stack,
        inkset,
        steps=args.steps,
        learning_rate=args.learning_rate,
        alpha_prior_weight=args.alpha_prior_weight,
        tile_pixels=args.tile_pixels,
    )
    alpha_stack = result["alpha_stack"]
    composite = render_alpha_stack(alpha_stack, inkset)
    composite_metrics = composite_error(composite, target_rgb)

    _write_plate_outputs(alpha_stack, inkset, alpha_dir, alpha8_dir, preview_dir)
    _save_rgb(composite, out / "composite_from_alpha_plates.png")
    _save_rgb(seed_result.rendered_rgb, out / "initial_guess_composite.png")
    _write_absdiff(target_rgb, composite, out / "source_vs_alpha_composite_absdiff_x4.png")
    _write_contact_sheet(working, composite, alpha_stack, inkset, out / "contact_sheet.png")
    np.savez_compressed(out / "alpha_stack_float32.npz", alpha_stack=alpha_stack.astype(np.float32))

    metadata = {
        "target": {
            "source_image": str(args.image),
            "target_mode": args.target_mode,
            "crop_size_px": list(target.size),
            "working_size_px": list(working.size),
            "source_variant": source_variant,
        },
        "solve": {
            "backend": "jax_soft_alpha_direct",
            "steps": args.steps,
            "learning_rate": args.learning_rate,
            "alpha_prior_weight": args.alpha_prior_weight,
            "tile_pixels": args.tile_pixels,
            "loss_history": result["loss_history"],
            "initial_metrics": seed_result.metrics,
            "final_metrics": composite_metrics,
        },
        "inkset": inkset.to_jsonable(),
        "outputs": {
            "alpha16": str(alpha_dir),
            "alpha8": str(alpha8_dir),
            "plate_previews": str(preview_dir),
            "composite": str(out / "composite_from_alpha_plates.png"),
            "contact_sheet": str(out / "contact_sheet.png"),
            "alpha_stack_npz": str(out / "alpha_stack_float32.npz"),
        },
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"out_dir": str(out), "final_metrics": composite_metrics}, indent=2))
    return 0


def _parse_rgb(value: str) -> tuple[int, int, int]:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("--paper-rgb must be r,g,b")
    return tuple(int(np.clip(part, 0, 255)) for part in parts)


def _select_target(source: Image.Image, mode: str) -> Image.Image:
    if mode == "full":
        return source.convert("RGB")
    if mode == "crop_artwork":
        cropped, _box = auto_crop_artwork(source)
        return cropped.convert("RGB")
    return _extract_right_composite(source)


def _extract_right_composite(layout: Image.Image) -> Image.Image:
    arr = np.asarray(layout.convert("RGB"), dtype=np.int16)
    h, w = arr.shape[:2]
    if w / max(h, 1) > 2.5:
        return layout.crop((int(w * 0.7973), int(h * 0.2208), int(w * 0.9206), int(h * 0.6883)))
    x_start = int(w * 0.72)
    region = arr[:, x_start:, :]
    paper = np.median(region.reshape(-1, 3), axis=0)
    delta = np.abs(region - paper[None, None, :]).sum(axis=2)
    saturation = region.max(axis=2) - region.min(axis=2)
    dark = region.mean(axis=2) < 224
    mask = (delta > 36) | (saturation > 42) | dark
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return layout.crop((int(w * 0.75), int(h * 0.15), int(w * 0.92), int(h * 0.78)))
    x0 = int(xs.min() + x_start)
    x1 = int(xs.max() + x_start)
    y0 = int(ys.min())
    y1 = int(ys.max())
    pad_x = max(4, int((x1 - x0) * 0.015))
    pad_y = max(4, int((y1 - y0) * 0.015))
    return layout.crop((
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(w, x1 + pad_x),
        min(h, y1 + pad_y),
    ))


def _upscale_target(
    target: Image.Image,
    *,
    out_dir: Path,
    method: str,
    scale: int,
    realesrgan_bin: str,
    realesrgan_model: str,
) -> tuple[Image.Image, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = max(1, int(scale))
    if method == "none" or scale == 1:
        return target.convert("RGB"), {"method": "none", "scale": 1}
    if method == "lanczos":
        return (
            target.resize((target.width * scale, target.height * scale), Image.Resampling.LANCZOS),
            {"method": "lanczos", "scale": scale},
        )
    executable = shutil.which(realesrgan_bin)
    if executable is None:
        return (
            target.resize((target.width * scale, target.height * scale), Image.Resampling.LANCZOS),
            {"method": "lanczos_fallback", "requested": "realesrgan", "scale": scale},
        )
    input_path = out_dir / "realesrgan_input.png"
    output_path = out_dir / f"target_realesrgan_{scale}x.png"
    target.save(input_path)
    command = [
        executable,
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "-s",
        str(scale),
        "-n",
        str(realesrgan_model),
        "-f",
        "png",
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0 or not output_path.exists():
        return (
            target.resize((target.width * scale, target.height * scale), Image.Resampling.LANCZOS),
            {
                "method": "lanczos_fallback",
                "requested": "realesrgan",
                "scale": scale,
                "stderr_tail": (completed.stderr or completed.stdout)[-1200:],
            },
        )
    return Image.open(output_path).convert("RGB"), {"method": "realesrgan", "scale": scale}


def solve_alpha_stack_jax(
    target_rgb: np.ndarray,
    seed_alpha: np.ndarray,
    inkset: InkSet,
    *,
    steps: int,
    learning_rate: float,
    alpha_prior_weight: float,
    tile_pixels: int,
) -> dict[str, Any]:
    import jax
    import jax.numpy as jnp

    h, w = target_rgb.shape[:2]
    plate_count = len(inkset.inks)
    pixels = h * w
    tile_pixels = max(1024, int(tile_pixels))
    target_flat = np.clip(target_rgb.reshape(-1, 3).astype(np.float32), 0.0, 1.0)
    seed_flat = np.clip(np.moveaxis(seed_alpha.astype(np.float32), 0, -1).reshape(-1, plate_count), 1e-5, 1.0 - 1e-5)
    alpha_out = np.zeros((pixels, plate_count), dtype=np.float32)
    inks = jnp.asarray([ink.rgb01 for ink in inkset.inks], dtype=jnp.float32)
    paper = jnp.asarray(np.asarray(inkset.paper_rgb, dtype=np.float32) / 255.0, dtype=jnp.float32)

    def render(alpha: Any, target_tile: Any) -> Any:
        out = jnp.broadcast_to(paper, target_tile.shape)
        for plate in range(alpha.shape[1]):
            a = alpha[:, plate, None]
            out = out * (1.0 - a) + inks[plate][None, :] * a
        return jnp.clip(out, 0.0, 1.0)

    def optimize_tile(target_tile: Any, seed_tile: Any) -> tuple[Any, Any]:
        seed_clipped = jnp.clip(seed_tile, 1e-5, 1.0 - 1e-5)
        init_logits = jnp.log(seed_clipped / (1.0 - seed_clipped))
        m = jnp.zeros_like(init_logits)
        v = jnp.zeros_like(init_logits)

        def loss_fn(params: Any) -> Any:
            alpha = jax.nn.sigmoid(params)
            comp = render(alpha, target_tile)
            rgb = jnp.mean((comp - target_tile) ** 2)
            value = jnp.mean((_luminance(comp) - _luminance(target_tile)) ** 2)
            prior = jnp.mean((alpha - seed_tile) ** 2)
            return rgb + 0.35 * value + float(alpha_prior_weight) * prior

        value_and_grad = jax.value_and_grad(loss_fn)

        def body(step: Any, state: tuple[Any, Any, Any]) -> tuple[Any, Any, Any]:
            logits, m_state, v_state = state
            _loss, grad = value_and_grad(logits)
            beta1 = 0.9
            beta2 = 0.999
            t = step + 1
            m_state = beta1 * m_state + (1.0 - beta1) * grad
            v_state = beta2 * v_state + (1.0 - beta2) * (grad * grad)
            mh = m_state / (1.0 - beta1**t)
            vh = v_state / (1.0 - beta2**t)
            logits = logits - float(learning_rate) * mh / (jnp.sqrt(vh) + 1e-8)
            logits = jnp.clip(logits, -9.0, 9.0)
            return logits, m_state, v_state

        logits, _m, _v = jax.lax.fori_loop(0, max(1, int(steps)), body, (init_logits, m, v))
        return jax.nn.sigmoid(logits), loss_fn(logits)

    optimize_tile_jit = jax.jit(optimize_tile)

    tile_losses: list[float] = []
    for start in range(0, pixels, tile_pixels):
        end = min(pixels, start + tile_pixels)
        target_tile = target_flat[start:end]
        seed_tile = seed_flat[start:end]
        valid = end - start
        if valid < tile_pixels:
            pad = tile_pixels - valid
            target_tile = np.pad(target_tile, ((0, pad), (0, 0)), mode="edge")
            seed_tile = np.pad(seed_tile, ((0, pad), (0, 0)), mode="edge")
        alpha_tile, loss = optimize_tile_jit(
            jnp.asarray(target_tile, dtype=jnp.float32),
            jnp.asarray(seed_tile, dtype=jnp.float32),
        )
        alpha_np = np.asarray(alpha_tile, dtype=np.float32)[:valid]
        alpha_out[start:end] = alpha_np
        loss_float = float(loss)
        tile_losses.append(loss_float)
        print(
            f"[alpha-solve] pixels={end:08d}/{pixels:08d} tile_loss={loss_float:.7f}",
            flush=True,
        )
    alpha_stack = np.moveaxis(alpha_out.reshape(h, w, plate_count), -1, 0)
    return {"alpha_stack": alpha_stack.astype(np.float32), "loss_history": tile_losses}


def _luminance(rgb: Any) -> Any:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _write_plate_outputs(
    alpha_stack: np.ndarray,
    inkset: InkSet,
    alpha_dir: Path,
    alpha8_dir: Path,
    preview_dir: Path,
) -> None:
    for idx, ink in enumerate(inkset.inks):
        slug = _slug(ink.label)
        alpha = np.clip(alpha_stack[idx], 0.0, 1.0)
        alpha16 = (alpha * 65535.0 + 0.5).astype(np.uint16)
        Image.fromarray(alpha16, mode="I;16").save(alpha_dir / f"{idx + 1:02d}_{slug}_alpha16.png")
        alpha8 = (alpha * 255.0 + 0.5).astype(np.uint8)
        Image.fromarray(alpha8, mode="L").save(alpha8_dir / f"{idx + 1:02d}_{slug}_alpha8.png")
        color = np.asarray(ink.rgb, dtype=np.float32) / 255.0
        preview = np.ones((*alpha.shape, 3), dtype=np.float32) * (1.0 - alpha[..., None]) + color[None, None, :] * alpha[..., None]
        _save_rgb(preview, preview_dir / f"{idx + 1:02d}_{slug}_preview.png")


def _save_rgb(rgb: np.ndarray, path: Path) -> None:
    Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8), "RGB").save(path)


def _write_absdiff(source: np.ndarray, composite: np.ndarray, path: Path) -> None:
    diff = np.clip(np.abs(source - composite) * 4.0, 0.0, 1.0)
    _save_rgb(diff, path)


def _write_contact_sheet(
    target: Image.Image,
    composite: np.ndarray,
    alpha_stack: np.ndarray,
    inkset: InkSet,
    path: Path,
) -> None:
    thumbs = [target.convert("RGB"), Image.fromarray(np.clip(composite * 255.0, 0, 255).astype(np.uint8), "RGB")]
    for idx, ink in enumerate(inkset.inks):
        alpha = alpha_stack[idx]
        color = np.asarray(ink.rgb, dtype=np.float32) / 255.0
        preview = np.ones((*alpha.shape, 3), dtype=np.float32) * (1.0 - alpha[..., None]) + color[None, None, :] * alpha[..., None]
        thumbs.append(Image.fromarray(np.clip(preview * 255.0, 0, 255).astype(np.uint8), "RGB"))
    cell_w = 360
    cell_h = 420
    cols = 3
    rows = int(np.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    labels = ["target", "composite", *[ink.label for ink in inkset.inks]]
    for idx, thumb in enumerate(thumbs):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        fitted = thumb.copy()
        fitted.thumbnail((cell_w - 36, cell_h - 64), Image.Resampling.LANCZOS)
        sheet.paste(fitted, (x + (cell_w - fitted.width) // 2, y + 18))
        draw.text((x + 18, y + cell_h - 34), labels[idx], fill=(0, 0, 0), font=font)
    sheet.save(path)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
