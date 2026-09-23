"""Shared overprint renderer for solving, training, previews, and audits."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from plotter_separation.inkset import InkSet


def render_alpha_stack(
    alpha_stack: NDArray[np.float32],
    inkset: InkSet,
) -> NDArray[np.float32]:
    """Composite per-plate alpha maps using the exact InkSet colors."""
    alpha = np.clip(np.asarray(alpha_stack, dtype=np.float32), 0.0, 1.0)
    if alpha.ndim != 3:
        raise ValueError("alpha_stack must have shape (plates, height, width)")
    if alpha.shape[0] != len(inkset.inks):
        raise ValueError("alpha_stack plate count must match InkSet")
    h, w = alpha.shape[1:]
    paper = np.asarray(inkset.paper_rgb, dtype=np.float32) / 255.0
    out = np.broadcast_to(paper, (h, w, 3)).copy()
    for plate_alpha, ink in zip(alpha, inkset.inks, strict=True):
        color = ink.rgb01.reshape(1, 1, 3)
        effective_alpha = np.clip(plate_alpha * float(ink.opacity), 0.0, 1.0)
        out = out * (1.0 - effective_alpha[..., None]) + color * effective_alpha[..., None]
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def composite_error(
    rendered: NDArray[np.float32],
    target: NDArray[np.float32],
) -> dict[str, float]:
    rendered = np.clip(np.asarray(rendered, dtype=np.float32), 0.0, 1.0)
    target = np.clip(np.asarray(target, dtype=np.float32), 0.0, 1.0)
    if rendered.shape != target.shape:
        raise ValueError("rendered and target must have matching shape")
    delta = rendered - target
    return {
        "rgb_rmse": round(float(np.sqrt(np.mean(delta * delta))), 6),
        "rgb_mae": round(float(np.mean(np.abs(delta))), 6),
    }


__all__ = ["composite_error", "render_alpha_stack"]
