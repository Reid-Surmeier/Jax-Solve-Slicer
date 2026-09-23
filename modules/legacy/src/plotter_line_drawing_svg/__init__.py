"""Line-drawing SVG markmaking for plotter plate outputs."""

from plotter_line_drawing_svg.markmaking import (
    CoverageConfig,
    Ink,
    InkSet,
    MarkPath,
    alpha_masks_to_budget_solved_paths,
    alpha_masks_to_coverage_paths,
    retain_paths_per_plate,
    write_plate_svgs,
)

__all__ = [
    "CoverageConfig",
    "Ink",
    "InkSet",
    "MarkPath",
    "alpha_masks_to_budget_solved_paths",
    "alpha_masks_to_coverage_paths",
    "retain_paths_per_plate",
    "write_plate_svgs",
]
