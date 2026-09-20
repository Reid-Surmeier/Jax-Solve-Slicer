# Preserved legacy stages

The minimal dependency closure for the working alpha solver and SVG/animation commands is copied byte for byte. `provenance.json` pins every file. `testing/check.py` catches accidental edits.

The SVG source retains its MIT license in `SVG-LICENSE`. The solver's pinned upstream `pyproject.toml` declares MIT; that upstream checkout contains no standalone license file. The source belongs to the owner's `ReidSurmeier/plotter-separation-rebuild` project; retain this provenance when distributing it.

Run the unchanged solver through `scripts/generate_micron_alpha_plates.py`. Run the SVG commands with `PYTHONPATH=modules/legacy/src`. Runtime dependencies are installed packages, never `repos/` references.
