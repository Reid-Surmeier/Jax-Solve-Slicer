from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plotter_line_drawing_svg.manifests import sha256_file


@dataclass(frozen=True)
class SvgLayer:
    index: int
    label: str
    color: str
    luminance: float
    opening: str
    paths: tuple[str, ...]
    closing: str


@dataclass(frozen=True)
class ParsedSvg:
    preamble: str
    layers: tuple[SvgLayer, ...]
    suffix: str
    artwork_rect: tuple[float, float, float, float] | None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Animate a layered coverage-mark SVG from light inks to dark inks."
    )
    parser.add_argument("svg", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--output-name", default="light_to_dark_mark_build.mp4")
    parser.add_argument("--fps", type=int, default=18)
    parser.add_argument("--frames-per-layer", type=int, default=14)
    parser.add_argument("--start-hold-frames", type=int, default=10)
    parser.add_argument("--end-hold-frames", type=int, default=30)
    parser.add_argument("--width-px", type=int, default=1080)
    parser.add_argument("--keep-frame-svgs", action="store_true")
    args = parser.parse_args()

    if shutil.which("rsvg-convert") is None:
        raise RuntimeError("rsvg-convert is required to rasterize SVG frames")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to encode MP4")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = args.out_dir / "frames"
    frame_svgs_dir = args.out_dir / "frame_svgs"
    frames_dir.mkdir(parents=True, exist_ok=True)
    if args.keep_frame_svgs:
        frame_svgs_dir.mkdir(parents=True, exist_ok=True)

    parsed = parse_layered_svg(args.svg.read_text(encoding="utf-8"))
    ordered_layers = tuple(sorted(parsed.layers, key=lambda layer: layer.luminance, reverse=True))
    frame_count = render_animation_frames(
        parsed,
        ordered_layers=ordered_layers,
        frames_dir=frames_dir,
        frame_svgs_dir=frame_svgs_dir if args.keep_frame_svgs else None,
        width_px=args.width_px,
        frames_per_layer=args.frames_per_layer,
        start_hold_frames=args.start_hold_frames,
        end_hold_frames=args.end_hold_frames,
    )
    output_mp4 = args.out_dir / args.output_name
    encode_mp4(frames_dir, output_mp4, fps=args.fps)

    manifest = {
        "source_svg": args.svg.name,
        "source_svg_sha256": sha256_file(args.svg),
        "output_mp4": output_mp4.name,
        "fps": args.fps,
        "frame_count": frame_count,
        "width_px": args.width_px,
        "frames_per_layer": args.frames_per_layer,
        "start_hold_frames": args.start_hold_frames,
        "end_hold_frames": args.end_hold_frames,
        "layer_order": [
            {
                "label": layer.label,
                "color": layer.color,
                "luminance": round(layer.luminance, 6),
                "path_count": len(layer.paths),
            }
            for layer in ordered_layers
        ],
    }
    (args.out_dir / "animation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.out_dir / "index.html").write_text(index_html(manifest), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


def parse_layered_svg(svg_text: str) -> ParsedSvg:
    group_pattern = re.compile(r"(?P<group><g\b[^>]*>.*?</g>)", re.DOTALL)
    groups = list(group_pattern.finditer(svg_text))
    if not groups:
        raise ValueError("SVG has no top-level layer groups")
    preamble = svg_text[: groups[0].start()]
    suffix = svg_text[groups[-1].end() :]
    layers = []
    for index, match in enumerate(groups):
        group = match.group("group")
        open_match = re.match(r"(?P<opening><g\b[^>]*>)(?P<body>.*)(?P<closing></g>)", group, re.DOTALL)
        if open_match is None:
            raise ValueError(f"could not parse layer group {index}")
        opening = open_match.group("opening")
        body = open_match.group("body")
        closing = open_match.group("closing")
        paths = tuple(re.findall(r"\s*<path\b[^>]*/>", body, flags=re.DOTALL))
        color = layer_color(opening, paths)
        layers.append(
            SvgLayer(
                index=index,
                label=layer_label(opening, fallback=f"layer {index + 1}"),
                color=color,
                luminance=relative_luminance(hex_to_rgb(color)),
                opening=opening,
                paths=paths,
                closing=closing,
            )
        )
    return ParsedSvg(
        preamble=preamble,
        layers=tuple(layers),
        suffix=suffix,
        artwork_rect=artwork_rect(svg_text),
    )


def render_animation_frames(
    parsed: ParsedSvg,
    *,
    ordered_layers: tuple[SvgLayer, ...],
    frames_dir: Path,
    frame_svgs_dir: Path | None,
    width_px: int,
    frames_per_layer: int,
    start_hold_frames: int,
    end_hold_frames: int,
) -> int:
    frame_index = 0
    empty_svg = compose_frame_svg(parsed, ordered_layers=ordered_layers, layer_progress={})
    for _ in range(start_hold_frames):
        write_frame(empty_svg, frame_index, frames_dir, frame_svgs_dir, width_px=width_px)
        frame_index += 1

    layer_progress: dict[int, float] = {}
    for layer in ordered_layers:
        for step in range(frames_per_layer):
            raw_t = (step + 1) / max(frames_per_layer, 1)
            layer_progress[layer.index] = smoothstep(raw_t)
            svg = compose_frame_svg(parsed, ordered_layers=ordered_layers, layer_progress=layer_progress)
            write_frame(svg, frame_index, frames_dir, frame_svgs_dir, width_px=width_px)
            frame_index += 1
        layer_progress[layer.index] = 1.0

    final_svg = compose_frame_svg(parsed, ordered_layers=ordered_layers, layer_progress=layer_progress)
    for _ in range(end_hold_frames):
        write_frame(final_svg, frame_index, frames_dir, frame_svgs_dir, width_px=width_px)
        frame_index += 1
    return frame_index


def compose_frame_svg(
    parsed: ParsedSvg,
    *,
    ordered_layers: tuple[SvgLayer, ...],
    layer_progress: dict[int, float],
) -> str:
    preamble = crop_preamble_to_artwork(parsed.preamble, parsed.artwork_rect)
    parts = [preamble]
    # Reveal timing is controlled by ordered_layers, but compositing must remain
    # in the original SVG order. SVG alpha blending is order-dependent, so
    # reordering groups changes the solved output color.
    _ = ordered_layers
    for layer in parsed.layers:
        progress = float(layer_progress.get(layer.index, 0.0))
        if progress <= 0.0:
            continue
        keep_count = int(math.ceil(len(layer.paths) * min(progress, 1.0)))
        if keep_count <= 0:
            continue
        parts.append(layer.opening)
        parts.extend(layer.paths[:keep_count])
        parts.append(layer.closing)
    parts.append(parsed.suffix)
    return "\n".join(parts)


def write_frame(
    svg: str,
    frame_index: int,
    frames_dir: Path,
    frame_svgs_dir: Path | None,
    *,
    width_px: int,
) -> None:
    if frame_svgs_dir is None:
        svg_path = frames_dir / f"frame_{frame_index:05d}.svg"
        delete_svg = True
    else:
        svg_path = frame_svgs_dir / f"frame_{frame_index:05d}.svg"
        delete_svg = False
    png_path = frames_dir / f"frame_{frame_index:05d}.png"
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-w", str(width_px), str(svg_path), "-o", str(png_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if delete_svg:
        svg_path.unlink(missing_ok=True)


def encode_mp4(frames_dir: Path, output_mp4: Path, *, fps: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%05d.png"),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def crop_preamble_to_artwork(
    preamble: str,
    rect: tuple[float, float, float, float] | None,
) -> str:
    if rect is None:
        return preamble
    rect_x, rect_y, rect_w, rect_h = rect
    replacement = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{rect_w:.6f}mm" height="{rect_h:.6f}mm" '
        f'viewBox="{rect_x:.6f} {rect_y:.6f} {rect_w:.6f} {rect_h:.6f}">'
    )
    return re.sub(r"<svg\b[^>]*>", replacement, preamble, count=1, flags=re.DOTALL)


def artwork_rect(svg_text: str) -> tuple[float, float, float, float] | None:
    match = re.search(
        r'id="artwork_bounds"\s+x="([0-9.]+)"\s+y="([0-9.]+)"\s+width="([0-9.]+)"\s+height="([0-9.]+)"',
        svg_text,
    )
    if match is None:
        return None
    return tuple(float(match.group(index)) for index in range(1, 5))  # type: ignore[return-value]


def layer_color(opening: str, paths: tuple[str, ...]) -> str:
    match = re.search(r'data-ink-color="(#[0-9a-fA-F]{6})"', opening)
    if match:
        return match.group(1).lower()
    for path in paths:
        fill_match = re.search(r'fill="(#[0-9a-fA-F]{6})"', path)
        if fill_match:
            return fill_match.group(1).lower()
    return "#000000"


def layer_label(opening: str, *, fallback: str) -> str:
    match = re.search(r'inkscape:label="([^"]+)"', opening)
    if match:
        return match.group(1).lstrip("!")
    return fallback


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return (int(color[0:2], 16) / 255.0, int(color[2:4], 16) / 255.0, int(color[4:6], 16) / 255.0)


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(channel) for channel in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def index_html(manifest: dict[str, Any]) -> str:
    rows = "\n".join(
        f"<tr><td>{item['label']}</td><td>{item['color']}</td><td>{item['path_count']}</td>"
        f"<td>{item['luminance']}</td></tr>"
        for item in manifest["layer_order"]
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Light-to-dark SVG mark build</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: white; color: #111; }}
    video {{ max-width: min(92vw, 900px); border: 1px solid #ddd; background: white; }}
    table {{ border-collapse: collapse; margin-top: 24px; }}
    td, th {{ border-bottom: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  </style>
</head>
<body>
  <h1>Light-to-dark SVG mark build</h1>
  <p><a href="{Path(manifest['output_mp4']).name}">MP4</a> |
  <a href="animation_manifest.json">manifest</a> | <a href="frames/">frames</a></p>
  <video src="{Path(manifest['output_mp4']).name}" controls autoplay muted loop></video>
  <h2>Layer Order</h2>
  <table><thead><tr><th>layer</th><th>color</th><th>paths</th><th>luminance</th></tr></thead>
  <tbody>{rows}</tbody></table>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
