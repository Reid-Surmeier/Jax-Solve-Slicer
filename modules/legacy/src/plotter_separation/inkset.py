"""Image-adaptive ink selection and InkSet audits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from plotter_separation.color import chroma, luminance, rgb_delta_e76


@dataclass(frozen=True)
class PigmentCandidate:
    """One standard pigment candidate that can be selected by image evidence."""

    label: str
    rgb: tuple[int, int, int]
    roles: tuple[str, ...]


@dataclass(frozen=True)
class Ink:
    """One plate ink used everywhere in the render contract."""

    id: str
    label: str
    rgb: tuple[int, int, int]
    role: str
    opacity: float = 1.0

    @property
    def rgb01(self) -> NDArray[np.float32]:
        return (np.asarray(self.rgb, dtype=np.float32) / 255.0).astype(np.float32)


@dataclass(frozen=True)
class InkSet:
    """Exact inks used by solving, training, SVG emission, and audit."""

    inks: tuple[Ink, ...]
    paper_rgb: tuple[int, int, int] = (248, 245, 237)
    mode: str = "image_adaptive"

    @classmethod
    def image_adaptive(
        cls,
        image: Image.Image | NDArray[np.uint8] | NDArray[np.float32],
        *,
        plate_count: int | None = None,
        seed: int = 2001,
    ) -> InkSet:
        rgb = _image_to_rgb01(image)
        count = plate_count or estimate_plate_count(rgb)
        centers = _role_balanced_centers(rgb, count, seed=seed)
        used_labels: set[str] = set()
        inks = []
        for i, (center, role) in enumerate(centers):
            ink = _ink_from_center(i + 1, center, role=role, used_labels=used_labels)
            used_labels.add(ink.label)
            inks.append(ink)
        return cls(inks=tuple(inks))

    @classmethod
    def hull_optimal(
        cls,
        image: Image.Image | NDArray[np.uint8] | NDArray[np.float32],
        *,
        plate_count: int | None = None,
        seed: int = 2001,
    ) -> InkSet:
        """Tan & Gingold-style simplified convex hull palette.

        The N inks chosen are vertices of the simplified convex hull of source
        pixels — i.e., the inks span the source's actual color cloud rather
        than just being "distinct." Uses the *raw* hull-vertex RGB as the ink
        color; bypasses the standard-pigment catalog snap that would otherwise
        collapse hull vertices to nearby catalog colors and shrink coverage.
        For physical plotting on a fixed pigment set, use image_adaptive.
        """
        rgb = _image_to_rgb01(image)
        count = plate_count or estimate_plate_count(rgb)
        centers = _hull_vertex_centers(rgb, count, seed=seed)
        inks = []
        for i, (center, role) in enumerate(centers):
            rgb_int = tuple(int(round(float(c) * 255.0)) for c in center)
            label = f"hull_{i + 1:02d}"
            inks.append(Ink(id=f"plate_{i + 1:02d}", label=label, rgb=rgb_int, role=role))
        return cls(inks=tuple(inks), mode="hull_optimal")

    def audit(self, *, duplicate_delta_e: float = 8.0) -> dict[str, Any]:
        colors = np.asarray([ink.rgb01 for ink in self.inks], dtype=np.float32)
        if len(colors) <= 1:
            pairs: list[dict[str, Any]] = []
        else:
            de = rgb_delta_e76(colors[:, None, :], colors[None, :, :])
            pairs = []
            for i in range(len(self.inks)):
                for j in range(i + 1, len(self.inks)):
                    if float(de[i, j]) <= duplicate_delta_e:
                        pairs.append({
                            "a": self.inks[i].id,
                            "b": self.inks[j].id,
                            "delta_e76": round(float(de[i, j]), 4),
                            "a_rgb": self.inks[i].rgb,
                            "b_rgb": self.inks[j].rgb,
                        })
        lum = luminance(colors) if len(colors) else np.array([], dtype=np.float32)
        roles: dict[str, int] = {}
        for ink in self.inks:
            roles[ink.role] = roles.get(ink.role, 0) + 1
        return {
            "mode": self.mode,
            "plate_count": len(self.inks),
            "duplicate_pairs": pairs,
            "role_counts": roles,
            "luminance_min": round(float(lum.min()), 4) if len(lum) else None,
            "luminance_max": round(float(lum.max()), 4) if len(lum) else None,
            "paper_rgb": self.paper_rgb,
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "paper_rgb": self.paper_rgb,
            "inks": [
                {
                    "id": ink.id,
                    "label": ink.label,
                    "rgb": ink.rgb,
                    "role": ink.role,
                    "opacity": ink.opacity,
                }
                for ink in self.inks
            ],
            "audit": self.audit(),
        }


def estimate_plate_count(rgb: NDArray[np.float32]) -> int:
    """Pick a starting plate count from color/detail complexity."""
    lum = luminance(rgb)
    sat = chroma(rgb)
    active = (lum < 0.94) | (sat > 0.045)
    if not np.any(active):
        return 4
    active_rgb = rgb[active]
    color_spread = float(np.mean(np.std(active_rgb, axis=0)))
    sat_p90 = float(np.percentile(sat[active], 90))
    dark_share = float(np.mean(lum[active] < 0.38))
    count = int(round(7 + color_spread * 16 + sat_p90 * 5 + dark_share * 3))
    return int(np.clip(count, 8, 16))


def _hull_vertex_centers(
    rgb: NDArray[np.float32],
    count: int,
    *,
    seed: int,
) -> list[tuple[NDArray[np.float32], str]]:
    """Pick `count` ink centers as vertices of a simplified convex hull of
    source pixels. Tan & Gingold's "Decomposing Images into Layers via
    RGB-space Geometry" (TOG 2018) proves that the convex hull of pixels is
    an upper bound on the palette that can reach every pixel; the simplified
    hull is a small palette whose hull approximates it.

    Implementation: take the actual convex hull (potentially hundreds of
    vertices), then iteratively keep the vertex farthest from the centroid
    of those already chosen — a greedy farthest-point sampling that
    maximizes spread.
    """
    from scipy.spatial import ConvexHull

    pixels = rgb.reshape(-1, 3).astype(np.float64)
    # Subsample for speed when image is large; hull is unchanged in expectation.
    rng = np.random.default_rng(seed)
    if len(pixels) > 20_000:
        idx = rng.choice(len(pixels), size=20_000, replace=False)
        pixels = pixels[idx]
    try:
        hull = ConvexHull(pixels)
        hull_pts = pixels[hull.vertices]
    except Exception:
        hull_pts = pixels

    # Greedy farthest-point sampling on the hull vertices.
    chosen: list[NDArray[np.float32]] = []
    chosen.append(hull_pts[np.argmin(np.sum(hull_pts, axis=1))])  # darkest vertex first
    while len(chosen) < count and len(chosen) < len(hull_pts):
        chosen_arr = np.asarray(chosen)
        # For each candidate, min distance to any chosen vertex.
        dists = np.min(np.linalg.norm(hull_pts[:, None, :] - chosen_arr[None, :, :], axis=2), axis=1)
        # Pick the candidate with the largest such min distance.
        chosen.append(hull_pts[int(np.argmax(dists))])

    centers = [np.asarray(c, dtype=np.float32) for c in chosen]
    # If we couldn't fill the count from hull alone, pad with role-balanced centers.
    if len(centers) < count:
        extras = _role_balanced_centers(rgb, count - len(centers), seed=seed + 1)
        centers.extend([c for c, _r in extras])

    # Assign roles via the same heuristic as _role_for_rgb so labels still make sense.
    return [(c, _role_for_rgb(c)) for c in centers[:count]]


def _role_balanced_centers(
    rgb: NDArray[np.float32],
    count: int,
    *,
    seed: int,
) -> list[tuple[NDArray[np.float32], str]]:
    lum = luminance(rgb)
    sat = chroma(rgb)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    masks = {
        "warm_light": (lum > 0.68) & (r > b + 0.035) & (sat > 0.035),
        "warm_skin": (lum > 0.34) & (lum <= 0.74) & (r > b + 0.045),
        "red_orange": (r > g + 0.035) & (r > b + 0.08) & (sat > 0.10),
        "background_green": (g >= r * 0.82) & (g >= b * 0.72) & (sat > 0.045),
        "cool_blue": (b > r * 0.82) & ((b > g * 0.84) | (g > r * 1.08)) & (sat > 0.045),
        "deep_shadow": (lum <= 0.36) & (lum > 0.16),
        "key_detail": lum <= 0.18,
    }
    role_order = (
        "warm_light",
        "warm_skin",
        "red_orange",
        "background_green",
        "cool_blue",
        "deep_shadow",
        "key_detail",
    )
    weights = 0.20 + sat * 1.65 + np.clip(0.78 - lum, 0.0, 1.0)
    available = [
        role
        for role in role_order
        if int(np.sum(masks[role])) >= max(16, rgb.shape[0] * rgb.shape[1] * 0.004)
    ]
    if not available:
        return [
            (center, _role_for_rgb(center))
            for center in _weighted_kmeans(
                rgb.reshape(-1, 3),
                np.ones(rgb.shape[0] * rgb.shape[1], dtype=np.float32),
                count,
                seed=seed,
            )
        ]

    counts = {role: 1 for role in available}
    remaining = max(0, count - len(available))
    masses = np.asarray(
        [float(np.sum(weights[masks[role]])) for role in available],
        dtype=np.float64,
    )
    role_caps = {
        "warm_light": max(1, round(count * 0.18)),
        "warm_skin": max(2, round(count * 0.26)),
        "red_orange": max(1, round(count * 0.16)),
        "background_green": max(1, round(count * 0.18)),
        "cool_blue": max(1, round(count * 0.18)),
        "deep_shadow": max(2, round(count * 0.22)),
        "key_detail": max(1, round(count * 0.10)),
    }
    while remaining > 0:
        best_role = None
        best_score = -1.0
        for role, mass in zip(available, masses, strict=True):
            if counts[role] >= role_caps[role]:
                continue
            score = float(mass) / float(counts[role] + 1)
            if score > best_score:
                best_role = role
                best_score = score
        if best_role is None:
            break
        counts[best_role] += 1
        remaining -= 1

    out: list[tuple[NDArray[np.float32], str]] = []
    for role in role_order:
        if role not in counts:
            continue
        mask = masks[role]
        pixels = rgb[mask]
        local_weights = weights[mask]
        centers = _weighted_kmeans(pixels, local_weights, counts[role], seed=seed + len(out) * 37)
        out.extend((center, role) for center in centers)
    out.sort(key=lambda item: float(luminance(item[0].reshape(1, 1, 3))[0, 0]), reverse=True)
    return out[:count]


def _weighted_kmeans(
    pixels: NDArray[np.float32],
    weights: NDArray[np.float32],
    count: int,
    *,
    seed: int,
) -> NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    count = max(1, min(int(count), len(pixels)))
    if len(pixels) > 40_000:
        probs = np.asarray(weights, dtype=np.float64)
        probs = probs / max(float(probs.sum()), 1e-6)
        choice = rng.choice(len(pixels), size=40_000, replace=False, p=probs)
        pixels = pixels[choice]
        weights = weights[choice]

    centers = _initial_centers(pixels, weights, count)
    for _ in range(12):
        d2 = np.sum((pixels[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(d2, axis=1)
        for i in range(count):
            mask = labels == i
            if np.any(mask):
                centers[i] = np.average(pixels[mask], axis=0, weights=weights[mask])
    order = np.argsort(luminance(centers))[::-1]
    return np.clip(centers[order], 0.0, 1.0).astype(np.float32)


def _initial_centers(
    pixels: NDArray[np.float32],
    weights: NDArray[np.float32],
    count: int,
) -> NDArray[np.float32]:
    centers = [pixels[int(np.argmax(weights))]]
    while len(centers) < count:
        existing = np.stack(centers, axis=0)
        d2 = np.min(np.sum((pixels[:, None, :] - existing[None, :, :]) ** 2, axis=2), axis=1)
        idx = int(np.argmax(d2 * weights))
        centers.append(pixels[idx])
    return np.stack(centers, axis=0).astype(np.float32)


_STANDARD_PIGMENTS: tuple[PigmentCandidate, ...] = (
    PigmentCandidate("cadmium yellow", (246, 205, 55), ("warm_light",)),
    PigmentCandidate("hansa yellow", (238, 185, 48), ("warm_light",)),
    PigmentCandidate("yellow ochre", (195, 142, 59), ("warm_light", "warm_skin")),
    PigmentCandidate("cadmium orange", (224, 102, 43), ("warm_skin", "red_orange")),
    PigmentCandidate("cadmium red", (190, 48, 35), ("red_orange",)),
    PigmentCandidate("quinacridone magenta", (169, 42, 93), ("red_orange", "warm_skin")),
    PigmentCandidate("burnt sienna", (135, 72, 48), ("warm_skin", "deep_shadow")),
    PigmentCandidate("raw umber", (86, 67, 48), ("deep_shadow", "key_detail")),
    PigmentCandidate("ivory black", (29, 27, 24), ("key_detail", "deep_shadow")),
    PigmentCandidate("viridian green", (0, 132, 96), ("background_green",)),
    PigmentCandidate("forest green", (38, 104, 70), ("background_green", "deep_shadow")),
    PigmentCandidate("sap green", (91, 117, 48), ("warm_skin",)),
    PigmentCandidate("cyan blue", (17, 139, 180), ("cool_blue",)),
    PigmentCandidate("cobalt blue", (48, 96, 174), ("cool_blue",)),
    PigmentCandidate("ultramarine blue", (43, 65, 145), ("cool_blue", "deep_shadow")),
    PigmentCandidate("cobalt violet", (109, 81, 145), ("red_orange",)),
)


def _ink_from_center(
    index: int,
    center: NDArray[np.float32],
    *,
    role: str | None = None,
    used_labels: set[str] | None = None,
) -> Ink:
    role = role or _role_for_rgb(center)
    used = used_labels or set()
    pigment = _select_standard_pigment(center, role=role, used_labels=used)
    return Ink(
        id=f"plate_{index:02d}",
        label=pigment.label,
        rgb=pigment.rgb,
        role=role,
    )


def _select_standard_pigment(
    center: NDArray[np.float32],
    *,
    role: str,
    used_labels: set[str],
) -> PigmentCandidate:
    candidates = [pigment for pigment in _STANDARD_PIGMENTS if role in pigment.roles]
    if not candidates:
        candidates = list(_STANDARD_PIGMENTS)
    center01 = np.asarray(center, dtype=np.float32)

    def score(pigment: PigmentCandidate) -> float:
        rgb01 = np.asarray(pigment.rgb, dtype=np.float32) / 255.0
        distance = float(np.sum((rgb01 - center01) ** 2))
        duplicate_penalty = 10.0 if pigment.label in used_labels else 0.0
        return distance + duplicate_penalty

    return min(candidates, key=score)


def _role_for_rgb(rgb: NDArray[np.float32]) -> str:
    r, g, b = (float(v) for v in rgb)
    lum = float(luminance(rgb.reshape(1, 1, 3))[0, 0])
    sat = float(chroma(rgb.reshape(1, 1, 3))[0, 0])
    if lum < 0.16:
        return "key_detail"
    if lum < 0.34:
        return "deep_shadow"
    if g > r * 1.08 and g >= b * 0.82:
        return "background_green"
    if b > r * 1.10 and b > g * 0.88:
        return "cool_blue"
    if r > b * 1.18 and g > b * 0.82:
        return "warm_skin"
    if sat < 0.08:
        return "neutral_value"
    return "chroma_accent"


def _image_to_rgb01(
    image: Image.Image | NDArray[np.uint8] | NDArray[np.float32],
) -> NDArray[np.float32]:
    if isinstance(image, Image.Image):
        arr = np.asarray(image.convert("RGB"))
    else:
        arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("image must be RGB")
    if np.issubdtype(arr.dtype, np.integer):
        return (arr.astype(np.float32) / 255.0).astype(np.float32)
    return np.clip(arr.astype(np.float32), 0.0, 1.0)


__all__ = ["Ink", "InkSet", "estimate_plate_count"]
