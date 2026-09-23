"""Source crop and upscale-variant diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from plotter_separation.color import chroma, luminance


@dataclass(frozen=True)
class SourceVariant:
    """One possible working image for solving/training."""

    name: str
    image: Image.Image
    metrics: dict[str, Any]


def auto_crop_artwork(
    source: Image.Image,
    *,
    padding_fraction: float = 0.015,
    min_active_fraction: float = 0.045,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop paper margins while ignoring low-density caption marks."""
    image = source.convert("RGB")
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    h, w = rgb.shape[:2]
    border = np.concatenate(
        [
            rgb[: max(1, h // 20), :, :].reshape(-1, 3),
            rgb[-max(1, h // 20) :, :, :].reshape(-1, 3),
            rgb[:, : max(1, w // 20), :].reshape(-1, 3),
            rgb[:, -max(1, w // 20) :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    paper = np.median(border, axis=0)
    distance_from_paper = np.sqrt(np.sum((rgb - paper[None, None, :]) ** 2, axis=2))
    lum = luminance(rgb)
    sat = chroma(rgb)
    paper_lum = float(luminance(paper.reshape(1, 1, 3))[0, 0])
    active = (distance_from_paper > 0.10) & ((sat > 0.045) | (lum < paper_lum - 0.10))
    if not np.any(active):
        return image, (0, 0, w, h)

    row_density = np.mean(active, axis=1)
    col_density = np.mean(active, axis=0)
    row_threshold = max(float(min_active_fraction), float(np.max(row_density)) * 0.28)
    col_threshold = max(float(min_active_fraction), float(np.max(col_density)) * 0.28)
    rows = _primary_density_run(row_density, threshold=row_threshold)
    cols = _primary_density_run(col_density, threshold=col_threshold)
    if rows.size == 0 or cols.size == 0:
        ys, xs = np.nonzero(active)
        rows = np.asarray([ys.min(), ys.max()])
        cols = np.asarray([xs.min(), xs.max()])

    pad = int(round(min(w, h) * float(padding_fraction)))
    left = max(0, int(cols.min()) - pad)
    top = max(0, int(rows.min()) - pad)
    right = min(w, int(cols.max()) + 1 + pad)
    bottom = min(h, int(rows.max()) + 1 + pad)
    if right <= left or bottom <= top:
        return image, (0, 0, w, h)
    return image.crop((left, top, right, bottom)), (left, top, right, bottom)


def make_source_variants(
    source: Image.Image,
    *,
    scale: int = 2,
) -> tuple[SourceVariant, ...]:
    """Create deterministic source variants before selecting a working image."""
    original = source.convert("RGB")
    variants = [
        SourceVariant("none", original, {"scale": 1, "risk": "baseline"}),
    ]
    if scale > 1:
        lanczos = original.resize(
            (original.width * scale, original.height * scale),
            Image.Resampling.LANCZOS,
        )
        variants.append(SourceVariant(
            "lanczos",
            lanczos,
            _variant_metrics(original, lanczos, scale=scale),
        ))
    return tuple(variants)


def make_working_source_variant(
    source: Image.Image,
    *,
    method: str = "none",
    scale: int = 2,
    out_dir: str | Path | None = None,
    realesrgan_bin: str = "realesrgan-ncnn-vulkan",
    realesrgan_model: str = "realesrgan-x4plus",
    realesrgan_tile_size: int = 256,
    realesrgan_gpu_id: str | None = None,
    realesrgan_jobs: str | None = None,
    realesrgan_timeout_s: int = 0,
) -> SourceVariant:
    """Create the selected source variant used by solving/training."""
    normalized = method.strip().lower().replace("-", "_")
    if normalized in {"none", "original"}:
        original = source.convert("RGB")
        return SourceVariant("none", original, {"scale": 1, "risk": "baseline"})
    if normalized in {"lanczos", "lanczos_2x", "lanczos_3x", "lanczos_4x"}:
        chosen_scale = _scale_from_method(normalized, default=scale)
        return _lanczos_variant(source, scale=chosen_scale)
    if normalized in {"realesrgan", "real_esrgan", "realesrgan_2x", "realesrgan_3x", "realesrgan_4x"}:
        chosen_scale = _scale_from_method(normalized, default=scale)
        return _realesrgan_variant(
            source,
            scale=chosen_scale,
            out_dir=out_dir,
            binary=realesrgan_bin,
            model=realesrgan_model,
            tile_size=realesrgan_tile_size,
            gpu_id=realesrgan_gpu_id,
            jobs=realesrgan_jobs,
            timeout_s=realesrgan_timeout_s,
        )
    raise ValueError(f"unknown source variant method: {method}")


def save_source_variants(
    variants: tuple[SourceVariant, ...],
    out_dir: str | Path,
) -> list[dict[str, Any]]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for variant in variants:
        path = out / f"source_{variant.name}.png"
        variant.image.save(path)
        records.append({
            "name": variant.name,
            "path": str(path),
            "size_px": list(variant.image.size),
            "metrics": variant.metrics,
        })
    return records


def _lanczos_variant(source: Image.Image, *, scale: int) -> SourceVariant:
    original = source.convert("RGB")
    chosen_scale = max(1, int(scale))
    if chosen_scale <= 1:
        return SourceVariant("none", original, {"scale": 1, "risk": "baseline"})
    upscaled = original.resize(
        (original.width * chosen_scale, original.height * chosen_scale),
        Image.Resampling.LANCZOS,
    )
    return SourceVariant(
        f"lanczos_{chosen_scale}x",
        upscaled,
        _variant_metrics(original, upscaled, scale=chosen_scale),
    )


def _realesrgan_variant(
    source: Image.Image,
    *,
    scale: int,
    out_dir: str | Path | None,
    binary: str,
    model: str,
    tile_size: int,
    gpu_id: str | None,
    jobs: str | None,
    timeout_s: int,
) -> SourceVariant:
    original = source.convert("RGB")
    chosen_scale = max(2, int(scale))
    executable = shutil.which(binary)
    if executable is None:
        raise RuntimeError(f"Real-ESRGAN binary not found: {binary}")
    if out_dir is None:
        temp_context = tempfile.TemporaryDirectory(prefix="plotter-realesrgan-")
        work = Path(temp_context.name)
    else:
        temp_context = None
        work = Path(out_dir)
        work.mkdir(parents=True, exist_ok=True)
    try:
        input_path = work / "realesrgan_input.png"
        output_path = work / f"source_realesrgan_{chosen_scale}x.png"
        original.save(input_path)
        command = [
            executable,
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-s",
            str(chosen_scale),
            "-n",
            str(model),
            "-t",
            str(max(0, int(tile_size))),
            "-f",
            "png",
        ]
        if gpu_id is not None and str(gpu_id).strip().lower() not in {"", "auto"}:
            command.extend(["-g", str(gpu_id)])
        if jobs is not None and str(jobs).strip():
            command.extend(["-j", str(jobs)])
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=float(timeout_s) if int(timeout_s) > 0 else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Real-ESRGAN timed out after {timeout_s}s while processing {input_path}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"Real-ESRGAN failed: {stderr[-1200:]}") from exc
        upscaled = Image.open(output_path).convert("RGB")
        metrics = _variant_metrics(original, upscaled, scale=chosen_scale)
        metrics["binary"] = executable
        metrics["model"] = model
        metrics["tile_size"] = int(tile_size)
        metrics["gpu_id"] = str(gpu_id) if gpu_id is not None else "auto"
        metrics["jobs"] = str(jobs) if jobs is not None else "default"
        metrics["timeout_s"] = int(timeout_s)
        metrics["stderr"] = completed.stderr[-800:] if completed.stderr else ""
        return SourceVariant(f"realesrgan_{chosen_scale}x", upscaled, metrics)
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def _scale_from_method(method: str, *, default: int) -> int:
    for scale in (2, 3, 4):
        if method.endswith(f"_{scale}x"):
            return scale
    return max(1, int(default))


def _variant_metrics(original: Image.Image, working: Image.Image, *, scale: int) -> dict[str, Any]:
    down = working.resize(original.size, Image.Resampling.LANCZOS)
    a = np.asarray(original, dtype=np.float32) / 255.0
    b = np.asarray(down, dtype=np.float32) / 255.0
    delta = b - a
    return {
        "scale": int(scale),
        "roundtrip_rgb_mae": round(float(np.mean(np.abs(delta))), 6),
        "roundtrip_rgb_rmse": round(float(np.sqrt(np.mean(delta * delta))), 6),
        "detail_shift": _detail_shift(a, b),
        "chroma_shift": round(float(np.mean(chroma(b) - chroma(a))), 6),
    }


def _detail_shift(a: NDArray[np.float32], b: NDArray[np.float32]) -> dict[str, float]:
    ga = _gradient_energy(luminance(a))
    gb = _gradient_energy(luminance(b))
    return {
        "source": round(float(ga), 6),
        "variant_downsampled": round(float(gb), 6),
        "ratio": round(float(gb / max(ga, 1e-8)), 6),
    }


def _gradient_energy(lum: NDArray[np.float32]) -> float:
    gy, gx = np.gradient(lum)
    return float(np.mean(np.sqrt(gx * gx + gy * gy)))


def _primary_density_run(density: NDArray[np.float32], *, threshold: float) -> NDArray[np.int64]:
    active = np.asarray(density) >= float(threshold)
    best: tuple[int, int] | None = None
    best_score = -1.0
    start: int | None = None
    for idx, is_active in enumerate(active):
        if bool(is_active) and start is None:
            start = idx
        is_last = idx == len(active) - 1
        if start is not None and (not bool(is_active) or is_last):
            end = idx if not bool(is_active) else idx + 1
            height = max(1, end - start)
            mass = float(np.sum(density[start:end]))
            score = mass * float(np.sqrt(height))
            if score > best_score:
                best = (start, end)
                best_score = score
            start = None
    if best is None:
        return np.asarray([], dtype=np.int64)
    return np.arange(best[0], best[1], dtype=np.int64)


__all__ = [
    "SourceVariant",
    "auto_crop_artwork",
    "make_source_variants",
    "make_working_source_variant",
    "save_source_variants",
]
