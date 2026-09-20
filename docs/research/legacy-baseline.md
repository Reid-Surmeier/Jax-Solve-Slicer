# Recovered baseline and Mixbox lineage

Investigation date: 2026-09-20. Resolution of [Recover the baseline and verify the Mixbox lineage](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/2). Read-only inspection of existing source, git state, and artifact metadata; no legacy programs, dependency installation, paid generation, or physical painting was run. Local source citations below are relative to the named checkout and pinned commit. Private source and artwork have not been copied into this public repository.

## Recommended baseline

Use `~/src/plotter-separation-rebuild` at `3047e9375ba8688f76144c89359387f1af706096` for upstream alpha solving, and `~/src/plotter-line-drawing-svg` at `ebb28918cafba8db13d33488c5ed0ea47c45826e` for existing mark generation/export. Both checkouts were clean. This follows the extracted SVG project's own [complete workflow](https://github.com/ReidSurmeier/plotter-line-drawing-svg/blob/ebb28918cafba8db13d33488c5ed0ea47c45826e/docs/animation-workflow.md) and [provenance](https://github.com/ReidSurmeier/plotter-line-drawing-svg/blob/ebb28918cafba8db13d33488c5ed0ea47c45826e/docs/provenance.md).

This is a recoverable code-and-input baseline, not yet a reproduced successful run. The immediate comparison should hold its input alpha plates constant while testing editable per-painting mark recipes, including shape and direction. Blender/Geometry Nodes remains a candidate for that editing experience. No upstream replacement or change of color physics is implied.

## Version inventory

Paths are under `/home/reidsurmeier/`.

| Checkout | HEAD and state | Interpretation |
| --- | --- | --- |
| `src/plotter-separation` | `53a2d65f76814f88da8017e6be013de4d2eeda09`, main; untracked `runs/` and `scripts/render_progressive_animation.py` | Maintained original JAX-to-open-strokes pipeline; preserve extra local evidence. |
| `src/plotter-separation-rebuild` | `3047e9375ba8688f76144c89359387f1af706096`, clean main | Recommended upstream alpha solver. |
| `src/plotter-line-drawing-svg` | `ebb28918cafba8db13d33488c5ed0ea47c45826e`, clean main | Recommended existing alpha-to-filled-marks implementation. |
| `plotter-separation-rebuild` | `b9e1796d6e0a7ce3f12c607814ee6dee6d45127c`, dirty main | Older preserved copy, including local animation evidence. |
| `plotter-separation-lithograph-next` | `ba0c7aa4cc6fc44d57272f49f694572cfe1a5543`, clean `lithograph-stroke-realization-next` | Separate experimental original-pipeline branch; not an automatic successor. |
| `orca/projects/plotter-image-animations` | `3f5c8f835a127ca06e518e381fed0ff3e4c7de52`, clean main | Exported media archive, not the generating implementation. |

Evidence: `git rev-parse`, `git log -1`, `git status --short`, `git branch --show-current`, and sanitized `git remote get-url origin` in these checkouts. Origins belong to historical account `ReidSurmeier`; current authorized interactive identity is `Reid-Surmeier`. Original/rebuild remote access returned 404 during initial discovery, which cannot distinguish private, renamed, or deleted repositories. Local source is available independently.

The old dirty rebuild lists modifications to `src/plotter_separation/animation/renderers/base.py`, `tests/test_proof_visualizer_smoke.py`, and `uv.lock`, plus untracked `scripts/render_monitor_chunk.py` and `docs/animation-runs/gallerist-office-12color-final/`. Direct byte comparison established that the renderer, test, chunk helper, `scripts/generate_micron_alpha_plates.py`, and `scripts/convert_micron_alpha_to_coverage_svg.py` match the newer clean checkout. The old lock was not established as equivalent. Preserve the old directory and artifacts; reviewing newer code loses none of those five inspected implementations. Rebuild `PROJECT.md` describes the animation custody and runtime checkpoint, but its historical test results are not fresh verification.

## Surviving input and interface

Fixture directory:

`/home/reidsurmeier/src/plotter-line-drawing-svg/runs/tumblr-790aa7518ed1/jax-alpha`

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `alpha_stack_float32.npz` | 2365899 | `01b7a11dc75b4ffc4dc3c3ca3acb89519d3a632ff1015e4d0e11ce0672c3f632` |
| `metadata.json` | 5620 | `0b47f4236a969257c09bf8268dab7d902ae91a32a4ef55b2f16fb2f150decf84` |

Read-only ZIP/NPY-header inspection confirms `alpha_stack.npy` is little-endian float32 with shape `(12, 957, 720)`. Metadata contains 12 ordered ink entries and records `solve.backend = jax_soft_alpha_direct`, 700 steps, learning rate 0.08, alpha prior weight 0.003, and tile size 65536 pixels. Those are recorded run settings, not newly validated quality metrics. No artwork is published here.

The seam is an ordered `(plates, height, width)` alpha stack plus metadata carrying the ordered ink set and paper. Rebuild `scripts/generate_micron_alpha_plates.py:103` initializes and solves it; line 122 writes the NPZ. Existing SVG generation interprets alpha as a local coverage target and emits filled marks with fixed opacity; density, size, and overlap produce tone. This differs from the original pipeline's open strokes. See the extracted project's [README](https://github.com/ReidSurmeier/plotter-line-drawing-svg/blob/ebb28918cafba8db13d33488c5ed0ea47c45826e/README.md) and [methodology](https://github.com/ReidSurmeier/plotter-line-drawing-svg/blob/ebb28918cafba8db13d33488c5ed0ea47c45826e/docs/methodology.md).

## What really uses Mixbox

Mixbox integration exists in the legacy source. It is not accurate to say the entire project lacked Mixbox.

| Path | Verified behavior |
| --- | --- |
| Original `backend/algorithms/decomposition/km_forward_render.py:23` | Imports `mixbox`. `mix_two` calls `mixbox.lerp`; `stack_pigments` and `forward_render_km` use RGB-to-latent conversion, latent blending, and latent-to-RGB conversion. |
| Original `backend/services/separation_v21_mokuhanga.py:27` | Imports `forward_render_km` and actually calls it at lines 236 and 319. This is a real older Mokuhanga rendering path. |
| Original `backend/services/v23/core/forward_render_jax.py:76` | `forward_render` performs ordered RGB alpha blending. It references pigment anchors associated with Mixbox but never calls the `_load_lut` helper, despite a docstring claiming transparent LUT support. |
| Rebuild `scripts/generate_micron_alpha_plates.py:256` | Per-image gradient optimization of alpha logits. Nested `render` at line 279 uses ordinary ordered RGB alpha blending. No Mixbox call in this solver. |
| Original `backend/mcp/tools/overlay.py:89` | Local empirical tier adds a mean RGB calibration bias to the T1 result; the tier selector alone does not establish a calibrated physical pigment renderer. `compare_render_tiers` explicitly assigns `t3_spectral = None` at line 306. |

Original source above is pinned to `53a2d65f76814f88da8017e6be013de4d2eeda09`; rebuild to `3047e9375ba8688f76144c89359387f1af706096`. The experimental `ba0c7aa4cc6fc44d57272f49f694572cfe1a5543` checkout also contains the actual Mixbox implementation and the Mokuhanga service import; searching its Python sources did not reveal a separate Mixbox call in its JAX forward renderer. This is a bounded inspection of the recovered versions, not a proof about every historical branch or remote host.

The JAX alpha solver optimizes this individual image using automatic differentiation and Adam-style updates. It is not evidence of a pretrained image-to-plates neural model. The selected surviving artifact records the RGB-alpha solver backend, so the recovered animation workflow should not be described as a verified Mixbox optical simulation. The older Mixbox path remains useful reference material, separately from the mark-recipe comparison.

## What remains unverified

- Fresh runtime installation, GPU availability, synthetic export, and visual baseline reproduction belong to the runnable-baseline task.
- Exact source-image provenance and complete regeneration of every historical animation are not established by finding code or matching metadata. Keep existing artwork local.
- No physical swatch measurements establish the accuracy of either RGB blending or Mixbox for the actual paint, substrate, drying order, or overlap process.
- Private GitHub upstream availability, missing remote-host work, and a different historical Mixbox/JAX integration remain unknown. The recovered source answers which inspected paths use Mixbox without ruling out unrecovered work.
- Recipe controls, Blender capabilities, and the shape/direction comparison still require their own decisions and prototypes.
