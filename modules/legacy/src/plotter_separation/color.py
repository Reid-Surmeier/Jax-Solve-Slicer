"""Color utilities used by audits and image-adaptive ink selection."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def srgb_to_linear(rgb: NDArray[np.floating]) -> NDArray[np.floating]:
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: NDArray[np.floating]) -> NDArray[np.floating]:
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(rgb, 1.0 / 2.4) - 0.055)


def srgb_to_lab(rgb: NDArray[np.floating]) -> NDArray[np.floating]:
    """Convert sRGB in [0, 1] to CIE Lab D65."""
    if rgb.dtype not in (np.float32, np.float64):
        rgb = rgb.astype(np.float32)
    linear = srgb_to_linear(rgb)
    r, g, b = linear[..., 0], linear[..., 1], linear[..., 2]
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    fx = _lab_f(x / 0.95047)
    fy = _lab_f(y)
    fz = _lab_f(z / 1.08883)
    return np.stack([116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)], axis=-1)


def delta_e76(lab_a: NDArray[np.floating], lab_b: NDArray[np.floating]) -> NDArray[np.floating]:
    diff = lab_a - lab_b
    return np.sqrt(np.sum(diff * diff, axis=-1))


def rgb_delta_e76(
    rgb_a: NDArray[np.floating],
    rgb_b: NDArray[np.floating],
) -> NDArray[np.floating]:
    return delta_e76(srgb_to_lab(rgb_a), srgb_to_lab(rgb_b))


def luminance(rgb: NDArray[np.floating]) -> NDArray[np.float32]:
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)


def chroma(rgb: NDArray[np.floating]) -> NDArray[np.float32]:
    return (np.max(rgb, axis=-1) - np.min(rgb, axis=-1)).astype(np.float32)


def _lab_f(t: NDArray[np.floating]) -> NDArray[np.floating]:
    eps = 0.008856
    return np.where(t > eps, np.cbrt(t), 7.787 * t + 16.0 / 116.0)


__all__ = [
    "chroma",
    "delta_e76",
    "linear_to_srgb",
    "luminance",
    "rgb_delta_e76",
    "srgb_to_lab",
    "srgb_to_linear",
]
