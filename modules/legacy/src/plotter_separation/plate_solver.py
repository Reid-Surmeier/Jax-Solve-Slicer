"""Plate-density initialization for the composite-first rebuild.

This is a seed generator, not the final inverse solver. Its job is to provide a
reasonable starting alpha stack while the differentiable composite realizer owns
the final visual target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from plotter_separation.color import chroma, luminance
from plotter_separation.inkset import InkSet
from plotter_separation.overprint import composite_error, render_alpha_stack


@dataclass(frozen=True)
class PlateSeedResult:
    alpha_stack: NDArray[np.float32]
    rendered_rgb: NDArray[np.float32]
    metrics: dict[str, Any]


def initialize_alpha_stack(
    source_rgb: NDArray[np.float32],
    inkset: InkSet,
    *,
    sigma: float | None = None,
) -> PlateSeedResult:
    """Create an initial alpha stack from image/ink color affinity."""
    source = np.clip(np.asarray(source_rgb, dtype=np.float32), 0.0, 1.0)
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("source_rgb must have shape (height, width, 3)")
    candidates = (float(sigma),) if sigma is not None else (0.16, 0.22, 0.28, 0.34, 0.42, 0.55)
    trials = []
    for candidate_sigma in candidates:
        alpha = _alpha_stack_for_sigma(source, inkset, sigma=float(candidate_sigma))
        rendered = render_alpha_stack(alpha, inkset)
        err = composite_error(rendered, source)
        trials.append((float(err["rgb_rmse"]), float(candidate_sigma), alpha, rendered, err))
    score, selected_sigma, alpha, rendered, err = min(trials, key=lambda item: item[0])
    del score
    candidate_metrics = [
        {
            "sigma": round(candidate_sigma, 4),
            "rgb_rmse": round(rmse, 6),
        }
        for rmse, candidate_sigma, _alpha, _rendered, _err in trials
    ]
    return PlateSeedResult(
        alpha_stack=alpha,
        rendered_rgb=rendered,
        metrics={
            "target": "initializer_only",
            **err,
            "sigma": round(selected_sigma, 4),
            "candidate_sigmas": candidate_metrics,
            "mean_alpha_by_plate": [round(float(v), 6) for v in alpha.mean(axis=(1, 2))],
        },
    )


def _alpha_stack_for_sigma(
    source: NDArray[np.float32],
    inkset: InkSet,
    *,
    sigma: float,
) -> NDArray[np.float32]:
    lum = luminance(source)
    sat = chroma(source)
    dark = np.clip((0.96 - lum) / 0.88, 0.0, 1.0)
    inks = np.asarray([ink.rgb01 for ink in inkset.inks], dtype=np.float32)
    diff = source[None, :, :, :] - inks[:, None, None, :]
    value_delta = lum[None, :, :] - luminance(inks)[:, None, None]
    chroma_delta = diff - value_delta[..., None]
    d2 = np.sum(chroma_delta * chroma_delta, axis=-1) * 1.55 + value_delta * value_delta * 0.38
    affinity = np.exp(-d2 / max(sigma * sigma, 1e-6)).astype(np.float32)

    role_gain = np.asarray([_role_gain(ink.role) for ink in inkset.inks], dtype=np.float32)
    alpha = affinity * role_gain[:, None, None] * (0.16 + dark[None, :, :] * 0.72 + sat[None, :, :] * 0.18)
    return _normalize_local_coverage(alpha)


def _normalize_local_coverage(alpha: NDArray[np.float32]) -> NDArray[np.float32]:
    total = np.sum(alpha, axis=0, keepdims=True)
    scale = np.where(total > 1.35, 1.35 / np.maximum(total, 1e-6), 1.0)
    return np.clip(alpha * scale, 0.0, 0.88).astype(np.float32)


def _role_gain(role: str) -> float:
    if role in {"key_detail", "deep_shadow"}:
        return 0.96
    if role in {"background_green", "cool_blue"}:
        return 0.78
    if role in {"warm_light"}:
        return 0.55
    return 0.72


__all__ = ["PlateSeedResult", "initialize_alpha_stack"]
