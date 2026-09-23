from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

PAGE_MM = (594.0, 841.0)
MARGIN_MM = 42.0
REFERENCE_MAX_SIDE = 192.0
REFERENCE_TILE_PX = 2.0


@dataclass(frozen=True)
class Ink:
    id: str
    label: str
    rgb: tuple[int, int, int]
    role: str = ""
    opacity: float = 1.0


@dataclass(frozen=True)
class InkSet:
    inks: tuple[Ink, ...]
    paper_rgb: tuple[int, int, int] = (255, 255, 255)
    mode: str = "metadata"


@dataclass(frozen=True)
class CoverageConfig:
    tile_px: int
    min_alpha: float = 0.025
    mark_opacity: float = 0.55
    max_bands_per_cell: int = 3
    max_paths_per_plate: int = 7200


@dataclass(frozen=True)
class MarkPath:
    path_id: str
    plate_index: int
    opacity: float
    d: str


def load_alpha_stack(jax_dir: Path) -> NDArray[np.float32]:
    npz_path = jax_dir / "alpha_stack_float32.npz"
    if not npz_path.exists():
        raise FileNotFoundError(npz_path)
    with np.load(npz_path) as data:
        alpha = data["alpha_stack"].astype(np.float32)
    if alpha.ndim != 3:
        raise ValueError(f"expected alpha stack with shape plate,height,width; got {alpha.shape}")
    return np.clip(alpha, 0.0, 1.0)


def load_inkset(jax_dir: Path) -> InkSet:
    metadata = json.loads((jax_dir / "metadata.json").read_text(encoding="utf-8"))
    inkset_data = metadata.get("inkset") or {}
    inks = []
    for item in inkset_data.get("inks", []):
        inks.append(
            Ink(
                id=str(item["id"]),
                label=str(item["label"]),
                rgb=tuple(int(v) for v in item["rgb"]),
                role=str(item.get("role", item["label"])),
                opacity=float(item.get("opacity", 1.0)),
            )
        )
    if not inks:
        raise ValueError("metadata.json does not contain inkset.inks")
    paper = tuple(int(v) for v in inkset_data.get("paper_rgb", (255, 255, 255)))
    return InkSet(inks=tuple(inks), paper_rgb=paper, mode=str(inkset_data.get("mode", "metadata")))


def auto_tile_px(width: int, height: int) -> int:
    scaled = REFERENCE_TILE_PX * (max(width, height) / REFERENCE_MAX_SIDE)
    return max(2, int(round(scaled)))


def alpha_masks_to_coverage_paths(
    alpha_stack: NDArray[np.float32],
    *,
    config: CoverageConfig,
) -> tuple[list[MarkPath], dict[str, Any]]:
    plate_count, height, width = alpha_stack.shape
    tile = max(2, int(config.tile_px))
    paths: list[MarkPath] = []
    paths_per_plate: list[int] = []
    angles = (0.0, math.pi / 2.0, math.pi / 4.0, -math.pi / 4.0, math.pi / 8.0, -math.pi / 8.0)
    max_per_cell = max(1, int(config.max_bands_per_cell))
    min_alpha = float(np.clip(config.min_alpha, 0.0, 0.95))
    mark_opacity = float(np.clip(config.mark_opacity, min_alpha, 1.0))

    for plate in range(plate_count):
        alpha = np.clip(alpha_stack[plate], 0.0, 1.0)
        base_angle = angles[plate % len(angles)]
        rects: list[tuple[str, float, float]] = []
        for y0 in range(0, height, tile):
            y1 = min(y0 + tile, height)
            for x0 in range(0, width, tile):
                x1 = min(x0 + tile, width)
                local = float(np.mean(alpha[y0:y1, x0:x1]))
                if local < min_alpha:
                    continue
                coverage = float(np.clip(local / max(mark_opacity, 1e-6), 0.035, 0.96))
                mark_count = max(1, min(max_per_cell, int(math.ceil(coverage * max_per_cell))))
                jitter = _hash_unit(plate, x0, y0, 11) - 0.5
                angle = base_angle + jitter * 0.55
                cell_paths = _coverage_cell_paths(
                    float(x0),
                    float(y0),
                    float(x1),
                    float(y1),
                    clip_bounds=(0.0, 0.0, float(width), float(height)),
                    angle=angle,
                    coverage=coverage,
                    mark_count=mark_count,
                    seed=(plate, x0, y0),
                )
                area_rank = local * (x1 - x0) * (y1 - y0)
                for d in cell_paths:
                    rects.append((d, mark_opacity, area_rank))
        rects.sort(key=lambda item: item[2], reverse=True)
        limited = rects[: max(0, int(config.max_paths_per_plate))]
        paths_per_plate.append(len(limited))
        for index, (d, opacity, _rank) in enumerate(limited):
            paths.append(MarkPath(f"coverage-p{plate:02d}-{index:05d}", plate, opacity, d))
    return paths, {"mode": "coverage_svg", "tile_px": tile, "paths_per_plate": paths_per_plate}


def retain_paths_per_plate(paths: list[MarkPath], retention: float) -> tuple[list[MarkPath], dict[str, Any]]:
    retention = float(np.clip(retention, 0.0, 1.0))
    by_plate: dict[int, list[MarkPath]] = {}
    for path in paths:
        by_plate.setdefault(int(path.plate_index), []).append(path)

    retained: list[MarkPath] = []
    before: list[int] = []
    after: list[int] = []
    for plate in sorted(by_plate):
        plate_paths = by_plate[plate]
        keep_count = int(math.ceil(len(plate_paths) * retention))
        if plate_paths and retention > 0.0:
            keep_count = max(1, keep_count)
        kept = plate_paths[:keep_count]
        before.append(len(plate_paths))
        after.append(len(kept))
        retained.extend(kept)
    return retained, {
        "mode": "ranked_prune",
        "path_retention": retention,
        "paths_per_plate_before_retention": before,
        "paths_per_plate_after_retention": after,
        "paths_per_plate": after,
    }


def alpha_masks_to_budget_solved_paths(
    alpha_stack: NDArray[np.float32],
    *,
    baseline_counts: list[int],
    config: CoverageConfig,
    scale: float,
) -> tuple[list[MarkPath], dict[str, Any]]:
    plate_count, height, width = alpha_stack.shape
    target_counts = [max(1, int(math.ceil(count * scale))) for count in baseline_counts]
    base_tile = max(2, int(config.tile_px))
    max_per_cell = max(1, int(config.max_bands_per_cell))
    min_alpha = float(np.clip(config.min_alpha, 0.0, 0.95))
    mark_opacity = float(np.clip(config.mark_opacity, min_alpha, 1.0))
    angles = (0.0, math.pi / 2.0, math.pi / 4.0, -math.pi / 4.0, math.pi / 8.0, -math.pi / 8.0)

    paths: list[MarkPath] = []
    paths_per_plate: list[int] = []
    tile_per_plate: list[int] = []
    coverage_scale_per_plate: list[float] = []

    for plate in range(plate_count):
        alpha = np.clip(alpha_stack[plate], 0.0, 1.0)
        target_count = max(1, target_counts[plate])
        solve_tile = max(base_tile, int(round(math.sqrt((width * height) / max(target_count * 1.65, 1)))))
        cells = _budget_cells(alpha, tile_px=solve_tile, min_alpha=min_alpha)
        if not cells:
            paths_per_plate.append(0)
            tile_per_plate.append(solve_tile)
            coverage_scale_per_plate.append(1.0)
            continue

        weights = np.asarray([cell["mass"] for cell in cells], dtype=np.float64)
        counts = _systematic_weighted_counts(weights, target_count, seed=(plate, solve_tile, target_count))
        desired_total = float(
            sum(
                np.clip(cell["local"] / max(mark_opacity, 1e-6), 0.035, 0.96) * cell["area"]
                for cell in cells
            )
        )
        selected_total = float(
            sum(
                np.clip(cells[idx]["local"] / max(mark_opacity, 1e-6), 0.035, 0.96) * cells[idx]["area"]
                for idx, count in enumerate(counts)
                if count > 0
            )
        )
        coverage_scale = float(np.clip(desired_total / max(selected_total, 1e-6), 0.72, 2.8))
        base_angle = angles[plate % len(angles)]
        emitted = 0

        for idx, count in enumerate(counts):
            if count <= 0:
                continue
            cell = cells[idx]
            jitter = _hash_unit(plate, int(cell["x0"]), int(cell["y0"]), 11) - 0.5
            angle = base_angle + jitter * 0.55
            coverage = float(np.clip((cell["local"] / max(mark_opacity, 1e-6)) * coverage_scale, 0.035, 0.96))
            cell_paths = _coverage_cell_paths(
                float(cell["x0"]),
                float(cell["y0"]),
                float(cell["x1"]),
                float(cell["y1"]),
                clip_bounds=(0.0, 0.0, float(width), float(height)),
                angle=angle,
                coverage=coverage,
                mark_count=min(max_per_cell * 4, int(count)),
                seed=(plate, int(cell["x0"]), int(cell["y0"])),
            )
            for d in cell_paths:
                paths.append(MarkPath(f"budget-p{plate:02d}-{emitted:05d}", plate, mark_opacity, d))
                emitted += 1

        paths_per_plate.append(emitted)
        tile_per_plate.append(solve_tile)
        coverage_scale_per_plate.append(round(coverage_scale, 4))

    return paths, {
        "mode": "alpha_budget_solve",
        "baseline_paths_per_plate": baseline_counts,
        "target_paths_per_plate": target_counts,
        "paths_per_plate": paths_per_plate,
        "tile_px": base_tile,
        "budget_tile_px_per_plate": tile_per_plate,
        "coverage_scale_per_plate": coverage_scale_per_plate,
    }


def write_plate_svgs(
    paths: list[MarkPath],
    inkset: InkSet,
    *,
    width_px: int,
    height_px: int,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plate_dir = out_dir / "plate_svgs"
    plate_dir.mkdir(parents=True, exist_ok=True)
    rect_mm = artwork_rect_mm(width_px, height_px)

    master_svg = out_dir / "master_coverage_svg.svg"
    master_svg.write_text(
        coverage_svg_document(
            paths,
            inkset,
            width_px=width_px,
            height_px=height_px,
            rect_mm=rect_mm,
            include_plate=None,
            title="Plotter Line Drawing SVG",
        ),
        encoding="utf-8",
    )
    plate_svgs = []
    for index, ink in enumerate(inkset.inks):
        plate_path = plate_dir / f"{index + 1:02d}_{slug(ink.label)}.svg"
        plate_path.write_text(
            coverage_svg_document(
                paths,
                inkset,
                width_px=width_px,
                height_px=height_px,
                rect_mm=rect_mm,
                include_plate=index,
                title=f"{index + 1:02d} {ink.label}",
            ),
            encoding="utf-8",
        )
        plate_svgs.append(str(plate_path))
    return {"master_svg": str(master_svg), "plate_svgs": plate_svgs, "artwork_rect_mm": rect_mm}


def coverage_svg_document(
    paths: list[MarkPath],
    inkset: InkSet,
    *,
    width_px: int,
    height_px: int,
    rect_mm: tuple[float, float, float, float],
    include_plate: int | None,
    title: str,
) -> str:
    rect_x, rect_y, rect_w, rect_h = rect_mm
    scale = rect_w / float(width_px)
    page_w, page_h = PAGE_MM
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'width="{page_w}mm" height="{page_h}mm" viewBox="0 0 {page_w:.3f} {page_h:.3f}">'
        ),
        f"  <title>{xml_escape(title)}</title>",
        (
            f'  <rect id="paper" x="0" y="0" width="{page_w:.3f}" height="{page_h:.3f}" '
            f'fill="{rgb_hex(inkset.paper_rgb)}"/>'
        ),
        (
            f'  <rect id="artwork_bounds" x="{rect_x:.3f}" y="{rect_y:.3f}" width="{rect_w:.3f}" '
            f'height="{rect_h:.3f}" fill="none" stroke="none" data-source-px="{width_px} {height_px}"/>'
        ),
    ]
    paths_by_plate: dict[int, list[MarkPath]] = {}
    for path in paths:
        paths_by_plate.setdefault(int(path.plate_index), []).append(path)
    for index, ink in enumerate(inkset.inks):
        if include_plate is not None and index != include_plate:
            continue
        color = rgb_hex(ink.rgb)
        pause = "!" if index > 0 else ""
        layer_label = f"{pause}{index + 1:02d} {ink.label}"
        lines.append(
            f'  <g id="{ink.id}" inkscape:groupmode="layer" inkscape:label="{xml_escape(layer_label)}" '
            f'data-plate-role="{xml_escape(ink.role)}" data-ink-color="{color}" '
            f'transform="translate({rect_x:.6f} {rect_y:.6f}) scale({scale:.9f})">'
        )
        for path in paths_by_plate.get(index, []):
            lines.append(
                f'    <path id="{path.path_id}" d="{path.d}" fill="{color}" '
                f'fill-opacity="{path.opacity:.3f}" stroke="none" '
                'data-mark-family="coverage_line_fill" data-primitive="fill"/>'
            )
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def rasterize_svg_artwork(
    svg_path: Path,
    *,
    source_size_px: tuple[int, int],
    out_full_png: Path,
    out_crop_png: Path,
    rect_mm: tuple[float, float, float, float],
) -> bool:
    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        return False
    subprocess.run([rsvg, str(svg_path), "-o", str(out_full_png)], check=True)
    page = Image.open(out_full_png).convert("RGB")
    page_w_px, page_h_px = page.size
    rect_x, rect_y, rect_w, rect_h = rect_mm
    page_w_mm, page_h_mm = PAGE_MM
    left = int(round(rect_x / page_w_mm * page_w_px))
    top = int(round(rect_y / page_h_mm * page_h_px))
    right = int(round((rect_x + rect_w) / page_w_mm * page_w_px))
    bottom = int(round((rect_y + rect_h) / page_h_mm * page_h_px))
    crop = page.crop((left, top, right, bottom)).resize(source_size_px, Image.Resampling.LANCZOS)
    crop.save(out_crop_png)
    return True


def write_contact_sheet(out_dir: Path, inkset: InkSet) -> None:
    items: list[tuple[str, Path]] = []
    for name in ("target_upscaled.png", "jax_composite_from_alpha_plates.png", "actual_svg_crop.png"):
        path = out_dir / name
        if path.exists():
            items.append((name.replace(".png", ""), path))
    for index, ink in enumerate(inkset.inks):
        path = out_dir / "plate_svgs" / f"{index + 1:02d}_{slug(ink.label)}.svg"
        if path.exists():
            items.append((f"{index + 1:02d} {ink.label}", path))
    cell_w = 360
    cell_h = 430
    cols = 3
    rows = int(math.ceil(len(items) / cols)) if items else 1
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for idx, (label, path) in enumerate(items):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        thumb = _thumbnail_for_contact(path, max_px=cell_h - 74)
        sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 16))
        draw.text((x + 18, y + cell_h - 38), label[:34], fill=(0, 0, 0), font=font)
    sheet.save(out_dir / "contact_sheet.png")


def artwork_rect_mm(width_px: int, height_px: int) -> tuple[float, float, float, float]:
    page_w, page_h = PAGE_MM
    max_w = page_w - 2.0 * MARGIN_MM
    max_h = page_h - 2.0 * MARGIN_MM
    scale = min(max_w / float(width_px), max_h / float(height_px))
    art_w = width_px * scale
    art_h = height_px * scale
    return ((page_w - art_w) * 0.5, (page_h - art_h) * 0.5, art_w, art_h)


def _coverage_cell_paths(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    clip_bounds: tuple[float, float, float, float],
    angle: float,
    coverage: float,
    mark_count: int,
    seed: tuple[int, int, int],
) -> list[str]:
    cell_w = max(x1 - x0, 1e-6)
    cell_h = max(y1 - y0, 1e-6)
    cell_area = cell_w * cell_h
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    dx = math.cos(angle)
    dy = math.sin(angle)
    nx = -dy
    ny = dx
    total_area = coverage * cell_area
    mark_area = total_area / max(mark_count, 1)
    base_length = min(math.hypot(cell_w, cell_h) * 1.65, max(cell_w, cell_h) * (0.95 + 0.85 * coverage))
    paths: list[str] = []
    clip_x0, clip_y0, clip_x1, clip_y1 = clip_bounds
    for idx in range(mark_count):
        offset = (idx - 0.5 * (mark_count - 1)) / max(mark_count, 1)
        jitter_x = (_hash_unit(*seed, idx, 3) - 0.5) * cell_w * 0.72
        jitter_y = (_hash_unit(*seed, idx, 7) - 0.5) * cell_h * 0.72
        mx = cx + offset * nx * cell_w * 0.45 + jitter_x
        my = cy + offset * ny * cell_h * 0.45 + jitter_y
        local_angle = angle + (_hash_unit(*seed, idx, 17) - 0.5) * 0.48
        local_dx = math.cos(local_angle)
        local_dy = math.sin(local_angle)
        local_nx = -local_dy
        local_ny = local_dx
        length = base_length * (0.72 + 0.55 * _hash_unit(*seed, idx, 13))
        band_width = max(0.35, mark_area / max(length, 1e-6))
        poly = [
            (
                mx - 0.5 * length * local_dx - 0.5 * band_width * local_nx,
                my - 0.5 * length * local_dy - 0.5 * band_width * local_ny,
            ),
            (
                mx + 0.5 * length * local_dx - 0.5 * band_width * local_nx,
                my + 0.5 * length * local_dy - 0.5 * band_width * local_ny,
            ),
            (
                mx + 0.5 * length * local_dx + 0.5 * band_width * local_nx,
                my + 0.5 * length * local_dy + 0.5 * band_width * local_ny,
            ),
            (
                mx - 0.5 * length * local_dx + 0.5 * band_width * local_nx,
                my - 0.5 * length * local_dy + 0.5 * band_width * local_ny,
            ),
        ]
        clipped = _clip_polygon_to_rect(poly, clip_x0, clip_y0, clip_x1, clip_y1)
        if len(clipped) >= 3:
            paths.append(_polygon_path_d(clipped))
    return paths


def _budget_cells(alpha: NDArray[np.float32], *, tile_px: int, min_alpha: float) -> list[dict[str, float]]:
    height, width = alpha.shape
    cells: list[dict[str, float]] = []
    for y0 in range(0, height, tile_px):
        y1 = min(y0 + tile_px, height)
        for x0 in range(0, width, tile_px):
            x1 = min(x0 + tile_px, width)
            local = float(np.mean(alpha[y0:y1, x0:x1]))
            if local < min_alpha:
                continue
            area = float((x1 - x0) * (y1 - y0))
            cells.append({"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1), "area": area, "local": local, "mass": local * area})
    return cells


def _systematic_weighted_counts(weights: NDArray[np.float64], count: int, *, seed: tuple[int, int, int]) -> NDArray[np.int32]:
    if count <= 0 or weights.size == 0:
        return np.zeros(weights.size, dtype=np.int32)
    total = float(np.sum(weights))
    if total <= 0.0:
        counts = np.zeros(weights.size, dtype=np.int32)
        counts[: min(count, weights.size)] = 1
        return counts
    offset = _hash_unit(*seed, 29)
    positions = (np.arange(count, dtype=np.float64) + offset) * (total / count)
    cdf = np.cumsum(weights)
    indices = np.searchsorted(cdf, positions, side="right")
    indices = np.clip(indices, 0, weights.size - 1)
    return np.bincount(indices, minlength=weights.size).astype(np.int32)


def _clip_polygon_to_rect(
    points: list[tuple[float, float]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> list[tuple[float, float]]:
    def clip_edge(
        poly: list[tuple[float, float]],
        inside: Any,
        intersect: Any,
    ) -> list[tuple[float, float]]:
        if not poly:
            return []
        out: list[tuple[float, float]] = []
        prev = poly[-1]
        prev_inside = inside(prev)
        for curr in poly:
            curr_inside = inside(curr)
            if curr_inside:
                if not prev_inside:
                    out.append(intersect(prev, curr))
                out.append(curr)
            elif prev_inside:
                out.append(intersect(prev, curr))
            prev = curr
            prev_inside = curr_inside
        return out

    eps = 1e-9
    poly = points
    poly = clip_edge(poly, lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * ((x0 - a[0]) / (b[0] - a[0] + eps))))
    poly = clip_edge(poly, lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * ((x1 - a[0]) / (b[0] - a[0] + eps))))
    poly = clip_edge(poly, lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * ((y0 - a[1]) / (b[1] - a[1] + eps)), y0))
    poly = clip_edge(poly, lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * ((y1 - a[1]) / (b[1] - a[1] + eps)), y1))
    return poly


def _polygon_path_d(points: list[tuple[float, float]]) -> str:
    first = points[0]
    parts = [f"M {first[0]:.3f},{first[1]:.3f}"]
    for x, y in points[1:]:
        parts.append(f"L {x:.3f},{y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def _hash_unit(*values: int) -> float:
    state = 2166136261
    for value in values:
        state ^= int(value) & 0xFFFFFFFF
        state = (state * 16777619) & 0xFFFFFFFF
    return state / 0xFFFFFFFF


def _thumbnail_for_contact(path: Path, *, max_px: int) -> Image.Image:
    if path.suffix.lower() == ".svg":
        png = path.with_suffix(".thumb.png")
        rsvg = shutil.which("rsvg-convert")
        if rsvg is not None:
            subprocess.run([rsvg, "-h", str(max_px), str(path), "-o", str(png)], check=True)
            image = Image.open(png).convert("RGB")
        else:
            image = Image.new("RGB", (max_px, max_px), (245, 245, 245))
    else:
        image = Image.open(path).convert("RGB")
    image.thumbnail((320, max_px), Image.Resampling.LANCZOS)
    return image


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except OSError:
        return ImageFont.load_default()


def rgb_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def slug(value: str) -> str:
    return re.sub(r"_+", "_", "".join(ch.lower() if ch.isalnum() else "_" for ch in value)).strip("_")
