"""Run separate blue-target and green-target JAX solves for one plastic layer."""

import hashlib
import json
from pathlib import Path
import runpy
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "modules/legacy"
OUT = ROOT / "docs/prototypes/pepsi-two-plate-lattice"
sys.path.insert(0, str(LEGACY / "src"))

from plotter_separation.inkset import Ink, InkSet  # noqa: E402
from plotter_separation.overprint import composite_error, render_alpha_stack  # noqa: E402
from plotter_separation.plate_solver import initialize_alpha_stack  # noqa: E402


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_path = ROOT / "docs/prototypes/pepsi-single-pass/source.png"
    source = Image.open(source_path).convert("RGB")
    target = np.asarray(source, dtype=np.float32) / 255
    luminance = target[..., 0]*.2126 + target[..., 1]*.7152 + target[..., 2]*.0722
    density = 1-luminance
    blue_weight = .5 + .5*np.tanh((target[..., 2]-target[..., 1])*6)
    solve = runpy.run_path(str(LEGACY / "scripts/generate_micron_alpha_plates.py"))["solve_alpha_stack_jax"]
    plates = []
    passes = {}
    for name, weight in (("blue", blue_weight), ("green", 1-blue_weight)):
        target_gray = 1-density*weight
        target_rgb = np.repeat(target_gray[..., None], 3, axis=-1).astype(np.float32)
        Image.fromarray(np.uint8(np.round(target_gray*255))).save(OUT / f"{name}-target.png")
        ink = InkSet(inks=(Ink(name, name, (0, 0, 0), "key_detail"),),
                     paper_rgb=(255, 255, 255), mode=f"{name}_target_black_geometry")
        seed = initialize_alpha_stack(target_rgb, ink)
        result = solve(target_rgb, seed.alpha_stack, ink, steps=700, learning_rate=.08,
                       alpha_prior_weight=.003, tile_pixels=65536)
        plate = result["alpha_stack"][0]
        plates.append(plate)
        Image.fromarray(np.uint16(np.round(plate*65535))).save(OUT / f"{name}-alpha16.png")
        Image.fromarray(np.uint8(np.round((1-plate)*255))).save(OUT / f"{name}-black-preview.png")
        passes[name] = {"target": f"{name}-target.png", "inkset": ink.to_jsonable(),
                        "loss_history": result["loss_history"],
                        "target_error": composite_error(render_alpha_stack(result["alpha_stack"], ink), target_rgb)}
    alpha = np.stack(plates)
    assert alpha.shape == (2, source.height, source.width)
    np.savez_compressed(OUT / "two-alpha-float32.npz", alpha=alpha)
    merged_tone = np.clip(1-alpha.sum(axis=0), 0, 1)
    Image.fromarray(np.uint8(np.round(merged_tone*255))).save(OUT / "merged-tonal-target.png")
    receipt = {"source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
               "source_size_px": [source.width, source.height],
               "target_split": "source luminance density weighted by blue-versus-green channel tanh; weights sum to one",
               "solver": "preserved solve_alpha_stack_jax run twice, once per source-derived color target",
               "steps_per_pass": 700, "learning_rate": .08,
               "alpha_prior_weight": .003, "tile_pixels": 65536, "passes": passes}
    (OUT / "solve-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"out": str(OUT), "errors": {name: p["target_error"] for name,p in passes.items()}}))


if __name__ == "__main__": main()
