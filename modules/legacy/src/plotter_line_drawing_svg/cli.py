from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from plotter_line_drawing_svg.manifests import portable_artifact_path, sha256_file
from plotter_line_drawing_svg.markmaking import (
    CoverageConfig,
    alpha_masks_to_budget_solved_paths,
    alpha_masks_to_coverage_paths,
    auto_tile_px,
    load_alpha_stack,
    load_inkset,
    rasterize_svg_artwork,
    retain_paths_per_plate,
    write_contact_sheet,
    write_plate_svgs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert alpha plates into layered line-drawing SVGs.")
    parser.add_argument("jax_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--tile-px", default="auto")
    parser.add_argument("--mark-opacity", type=float, default=0.55)
    parser.add_argument("--max-bands-per-cell", type=int, default=3)
    parser.add_argument("--min-alpha", type=float, default=0.025)
    parser.add_argument("--max-paths-per-plate", type=int, default=7200)
    parser.add_argument(
        "--budget-solve-scale",
        type=float,
        default=0.0,
        help="Regenerate a lower-count mark field at this fraction of baseline path counts.",
    )
    parser.add_argument(
        "--path-retention",
        type=float,
        default=1.0,
        help="Naively prune this fraction of ranked baseline paths per plate.",
    )
    args = parser.parse_args()

    alpha_stack = load_alpha_stack(args.jax_dir)
    inkset = load_inkset(args.jax_dir)
    if alpha_stack.shape[0] != len(inkset.inks):
        raise ValueError(f"alpha stack has {alpha_stack.shape[0]} plates but metadata has {len(inkset.inks)} inks")

    _, height, width = alpha_stack.shape
    tile_px = auto_tile_px(width, height) if args.tile_px == "auto" else max(2, int(args.tile_px))
    config = CoverageConfig(
        tile_px=tile_px,
        min_alpha=args.min_alpha,
        mark_opacity=args.mark_opacity,
        max_bands_per_cell=args.max_bands_per_cell,
        max_paths_per_plate=args.max_paths_per_plate,
    )

    baseline_paths, baseline_metrics = alpha_masks_to_coverage_paths(alpha_stack, config=config)
    if args.budget_solve_scale > 0.0:
        paths, path_metrics = alpha_masks_to_budget_solved_paths(
            alpha_stack,
            baseline_counts=[int(v) for v in baseline_metrics["paths_per_plate"]],
            config=config,
            scale=args.budget_solve_scale,
        )
    elif args.path_retention < 0.999999:
        paths, path_metrics = retain_paths_per_plate(baseline_paths, args.path_retention)
    else:
        paths, path_metrics = baseline_paths, baseline_metrics

    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = write_plate_svgs(paths, inkset, width_px=width, height_px=height, out_dir=args.out_dir)

    for source_name, dest_name in (
        ("target_upscaled.png", "target_upscaled.png"),
        ("composite_from_alpha_plates.png", "jax_composite_from_alpha_plates.png"),
    ):
        source = args.jax_dir / source_name
        if source.exists():
            shutil.copy2(source, args.out_dir / dest_name)

    rasterized = rasterize_svg_artwork(
        Path(artifacts["master_svg"]),
        source_size_px=(width, height),
        out_full_png=args.out_dir / "actual_svg_full.png",
        out_crop_png=args.out_dir / "actual_svg_crop.png",
        rect_mm=artifacts["artwork_rect_mm"],
    )
    if rasterized:
        preview = Image.open(args.out_dir / "actual_svg_crop.png").convert("RGB")
        preview.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        preview.save(args.out_dir / "actual_svg_preview.png")
    write_contact_sheet(args.out_dir, inkset)

    portable_artifacts = {
        "master_svg": portable_artifact_path(
            Path(artifacts["master_svg"]),
            output_root=args.out_dir,
        ),
        "plate_svgs": [
            portable_artifact_path(Path(path), output_root=args.out_dir)
            for path in artifacts["plate_svgs"]
        ],
        "artwork_rect_mm": artifacts["artwork_rect_mm"],
    }
    metadata = {
        "method": "coverage_line_fill",
        "source": args.jax_dir.resolve().name,
        "source_files": {
            name: sha256_file(args.jax_dir / name)
            for name in ("alpha_stack_float32.npz", "metadata.json")
        },
        "alpha_stack_shape": [int(v) for v in alpha_stack.shape],
        "settings": {
            "tile_px": tile_px,
            "mark_opacity": args.mark_opacity,
            "max_bands_per_cell": args.max_bands_per_cell,
            "min_alpha": args.min_alpha,
            "max_paths_per_plate": args.max_paths_per_plate,
            "budget_solve_scale": args.budget_solve_scale,
            "path_retention": args.path_retention,
        },
        "paths": path_metrics,
        "artifacts": portable_artifacts,
    }
    (args.out_dir / "coverage_svg_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (args.out_dir / "index.html").write_text(_index_html(metadata), encoding="utf-8")
    print(json.dumps({"out_dir": str(args.out_dir), "paths": path_metrics}, indent=2))
    return 0


def _index_html(metadata: dict) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Plotter Line Drawing SVG</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: #fff; color: #111; }}
    img {{ max-width: 48vw; height: auto; border: 1px solid #ddd; vertical-align: top; }}
    code {{ background: #f3f3f3; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>Plotter Line Drawing SVG</h1>
  <p><code>{metadata["paths"]["mode"]}</code></p>
  <p><a href="master_coverage_svg.svg">master SVG</a> | <a href="coverage_svg_metadata.json">metadata</a></p>
  <p><a href="actual_svg_crop.png"><img src="actual_svg_crop.png"></a> <a href="contact_sheet.png"><img src="contact_sheet.png"></a></p>
  <p><a href="plate_svgs/">plate SVGs</a></p>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
