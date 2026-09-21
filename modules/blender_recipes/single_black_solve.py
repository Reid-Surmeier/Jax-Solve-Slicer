"""Run the preserved JAX alpha solver on the supplied image with one black ink."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import sys

import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "modules" / "legacy"
sys.path.insert(0, str(LEGACY / "src"))

from plotter_separation.inkset import Ink, InkSet  # noqa: E402
from plotter_separation.overprint import composite_error, render_alpha_stack  # noqa: E402
from plotter_separation.plate_solver import initialize_alpha_stack  # noqa: E402


def main() -> None:
    source_path = ROOT / "docs/prototypes/pepsi-single-pass/source.png"
    output = ROOT / "docs/prototypes/pepsi-jax-one-black"
    output.mkdir(parents=True, exist_ok=True)
    source = Image.open(source_path).convert("RGB")
    gray = ImageOps.grayscale(source).convert("RGB")
    gray.save(output / "grayscale-target.png")
    target = np.asarray(gray, dtype=np.float32) / 255.0
    inkset = InkSet(inks=(Ink("black", "Black", (0, 0, 0), "key_detail"),), paper_rgb=(255, 255, 255), mode="single_black")
    seed = initialize_alpha_stack(target, inkset)
    solve = runpy.run_path(str(LEGACY / "scripts/generate_micron_alpha_plates.py"))["solve_alpha_stack_jax"]
    result = solve(target, seed.alpha_stack, inkset, steps=700, learning_rate=0.08, alpha_prior_weight=0.003, tile_pixels=65536)
    alpha = result["alpha_stack"]
    assert alpha.shape == (1, source.height, source.width)
    composite = render_alpha_stack(alpha, inkset)
    Image.fromarray(np.round(alpha[0] * 65535).astype(np.uint16)).save(output / "black-alpha16.png")
    Image.fromarray(np.round(composite * 255).astype(np.uint8)).save(output / "black-composite.png")
    np.savez_compressed(output / "black-alpha-float32.npz", alpha=alpha)
    receipt = {
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_size_px": [source.width, source.height],
        "target": "Pillow L grayscale, black on white RGB",
        "inkset": inkset.to_jsonable(),
        "solver": "preserved generate_micron_alpha_plates.py:solve_alpha_stack_jax",
        "steps": 700,
        "learning_rate": 0.08,
        "alpha_prior_weight": 0.003,
        "tile_pixels": 65536,
        "loss_history": result["loss_history"],
        "composite_error": composite_error(composite, target),
    }
    (output / "solve-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"output": str(output), "error": receipt["composite_error"]}))


if __name__ == "__main__":
    main()
