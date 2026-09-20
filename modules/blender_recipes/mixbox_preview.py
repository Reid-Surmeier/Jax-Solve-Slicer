"""PROTOTYPE: compare color models on the same RGB-solved alpha stack."""
import argparse
import importlib.metadata
import json
from pathlib import Path

import mixbox
import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alpha", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    with np.load(args.alpha / "alpha_stack_float32.npz", allow_pickle=False) as archive:
        plates = archive["alpha_stack"]
    inkset = json.loads((args.alpha / "metadata.json").read_text())["inkset"]
    inks, paper = inkset["inks"], tuple(inkset.get("paper_rgb", [255,255,255]))
    if plates.ndim != 3 or not plates.size or len(plates) != len(inks):
        raise ValueError("Alpha stack and palette must match")
    if not np.isfinite(plates).all() or plates.min() < 0 or plates.max() > 1:
        raise ValueError("Alpha values must be finite and in [0,1]")
    # Verify the pigment API; the unrelated PyPI 'mixbox' must not pass.
    blue, yellow = (0,33,133), (252,211,0)
    assert mixbox.lerp(blue,yellow,0) == blue
    assert mixbox.lerp(blue,yellow,1) == yellow
    assert mixbox.lerp(blue,yellow,.5) == (41,130,57)
    height, width = plates.shape[1:]
    latent = np.broadcast_to(mixbox.rgb_to_latent(paper), (height,width,mixbox.LATENT_SIZE)).copy()
    rgb = np.broadcast_to(np.asarray(paper,dtype=float), (height,width,3)).copy()
    for plate, ink in zip(plates, inks):
        alpha = plate[:, :, None]
        latent = latent * (1-alpha) + np.asarray(mixbox.rgb_to_latent(tuple(ink["rgb"]))) * alpha
        rgb = rgb * (1-alpha) + np.asarray(ink["rgb"]) * alpha
    # No deduplication/quantization: decode each pixel with the official API.
    decoded = np.asarray([mixbox.latent_to_rgb(tuple(pixel)) for pixel in latent.reshape(-1,7)], dtype=np.uint8).reshape(height,width,3)
    args.out.mkdir(parents=True,exist_ok=True)
    Image.fromarray(np.rint(rgb).astype(np.uint8)).save(args.out / "rgb-recomposition.png")
    Image.fromarray(decoded).save(args.out / "mixbox-recomposition.png")
    # Endpoint and order checks protect the compositing interpretation.
    zblue, zyellow = map(lambda color: np.asarray(mixbox.rgb_to_latent(color)), [blue,yellow])
    assert mixbox.latent_to_rgb(tuple((zblue+zyellow)/2)) == mixbox.lerp(blue,yellow,.5)
    (args.out / "mixbox.json").write_text(json.dumps({"distribution":"pymixbox","version":importlib.metadata.version("pymixbox"),"method":"Ordered latent interpolation, decoded once per pixel","diagnostic_only":True,"warning":"These plates were solved under RGB alpha blending, not optimized for Mixbox. Neither model is calibrated to this machine's paint.","rgb_vs_mixbox_rmse":float(np.sqrt(np.mean(((rgb-decoded)/255)**2))),"blue_yellow_half_mix":[41,130,57]},indent=2)+"\n")
    print("Official Mixbox diagnostic and RGB comparison saved; pigment API checks passed")


if __name__ == "__main__":
    main()
