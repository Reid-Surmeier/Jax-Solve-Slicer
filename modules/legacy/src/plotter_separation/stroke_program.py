"""Trainable plot program primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    import torch


Point = tuple[float, float]


def orientation_alignment_loss(
    stroke_centers: "torch.Tensor",
    stroke_thetas: "torch.Tensor",
    tangent_field: "torch.Tensor",
    coherence_field: "torch.Tensor",
) -> "torch.Tensor":
    """Penalize strokes misaligned with the local source structure tangent.

    Loss = mean( sin²(theta_stroke - tangent_source) * coherence_source ).
    The sin² form is invariant to 180-degree flips (a stroke pointing -theta
    aligns with form just as well as +theta). Coherence weighting means flat
    regions, where the tangent is undefined, contribute no penalty.

    stroke_centers: (N, 2) float tensor in pixel coordinates (x, y).
    stroke_thetas: (N,) float tensor of stroke axis angles in radians.
    tangent_field: (H, W) float tensor of source tangent angles.
    coherence_field: (H, W) float tensor in [0, 1].
    """
    import torch

    centers_long = stroke_centers.round().long()
    h, w = tangent_field.shape
    xs = centers_long[:, 0].clamp(0, w - 1)
    ys = centers_long[:, 1].clamp(0, h - 1)

    source_tangent = tangent_field[ys, xs]
    source_coherence = coherence_field[ys, xs]

    angle_diff = stroke_thetas - source_tangent
    misalign = torch.sin(angle_diff) ** 2
    return (misalign * source_coherence).mean()


def stroke_params_to_cubic(
    center: "torch.Tensor",
    theta: "torch.Tensor",
    length: "torch.Tensor",
    curvature: "torch.Tensor",
) -> tuple["torch.Tensor", "torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    """Project 6-DoF stroke parameters to 4 cubic Bezier control points.

    The trainable parameters (theta, length, curvature, plus width and the two
    components of center) replace free 2D control points to make the loss
    landscape no longer shape-invariant under worm deformations.

    center: tensor of shape (2,), stroke midpoint.
    theta: scalar, orientation of the stroke axis in radians.
    length: scalar, end-to-end length.
    curvature: scalar, signed perpendicular offset of the middle control points
        as a fraction of length. curvature=0 yields a straight stroke.
    """
    import torch

    direction = torch.stack([torch.cos(theta), torch.sin(theta)])
    normal = torch.stack([-torch.sin(theta), torch.cos(theta)])

    half = 0.5 * length
    p0 = center - half * direction
    p3 = center + half * direction

    # Middle control points sit at +/- 1/3 of length along the axis, offset
    # perpendicular by curvature * length. Symmetric offset keeps the stroke
    # axially symmetric so a structure-tangent prior pulls theta cleanly.
    offset = curvature * length * normal
    p1 = center - (length / 3.0) * direction + offset
    p2 = center + (length / 3.0) * direction + offset
    return p0, p1, p2, p3


@dataclass(frozen=True)
class StrokePrimitive:
    """One open plotted path assigned to a Plate."""

    plate_id: str
    points: tuple[Point, ...]
    width_mm: float
    opacity: float = 0.85
    family: str = "stroke"
    width_profile_mm: tuple[float, ...] = ()


@dataclass(frozen=True)
class FillPrimitive:
    """One filled value primitive assigned to a Plate."""

    plate_id: str
    polygon: tuple[Point, ...]
    opacity: float
    family: str = "value_fill"


@dataclass(frozen=True)
class StrokeProgram:
    """The trainable representation emitted as SVG after optimization."""

    strokes: tuple[StrokePrimitive, ...] = ()
    fills: tuple[FillPrimitive, ...] = ()

    def primitives_for_plate(self, plate_id: str) -> tuple[tuple[FillPrimitive, ...], tuple[StrokePrimitive, ...]]:
        return (
            tuple(fill for fill in self.fills if fill.plate_id == plate_id),
            tuple(stroke for stroke in self.strokes if stroke.plate_id == plate_id),
        )

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "fills": [
                {
                    "plate_id": fill.plate_id,
                    "polygon": fill.polygon,
                    "opacity": fill.opacity,
                    "family": fill.family,
                }
                for fill in self.fills
            ],
            "strokes": [
                {
                    "plate_id": stroke.plate_id,
                    "points": stroke.points,
                    "width_mm": stroke.width_mm,
                    "width_profile_mm": stroke.width_profile_mm,
                    "opacity": stroke.opacity,
                    "family": stroke.family,
                }
                for stroke in self.strokes
            ],
        }


__all__ = [
    "FillPrimitive",
    "Point",
    "StrokePrimitive",
    "StrokeProgram",
    "orientation_alignment_loss",
    "stroke_params_to_cubic",
]
