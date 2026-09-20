# Jax Solve Slicer

Recover the existing painting pipeline and explore editable mark-generation recipes for each painting.

[Blender prototype and editable file](docs/prototypes/blender-recipes/README.md) · [Wayfinder map](https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/1) · [Verified baseline](docs/reproduction/2026-09-20/README.md)

The existing Python solver and SVG generator are preserved byte for byte in `modules/legacy`. The first Blender prototype exposes three editable mark recipes and exports evaluated geometry as SVG. Official Mixbox recomposition is available as a diagnostic comparison; it is not yet a Mixbox-optimized solver.

The repository uses the agentic-workflow new-repo template with its Blender-hosted Python exception. Read [MODULES.md](MODULES.md) for the four modules. Agent instructions are generated from `.ruler/AGENTS.md`. The prototype interface remains provisional until a later specification.

## Run

Use Blender 4.3.2 and Python 3.11 for the checked prototype. `rsvg-convert` must be on PATH.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-prototype.txt
npm ci
BLENDER=/path/to/blender-4.3.2/blender npm run prototype
npm run check
```

The result is under `outputs/blender-prototype`. Generation refuses to replace an existing `.blend`, preserving manual edits. Use a new output directory when regenerating:

```bash
npm run prototype -- docs/reproduction/2026-09-20/alpha outputs/another-experiment
```

Edit and export an existing scene without reconstructing its graph:

```bash
/path/to/blender-4.3.2/blender -b my-edited-recipes.blend --python-exit-code 1 --python modules/blender_recipes/export_current.py -- outputs/edited.svg
```

Blender automation currently uses its native Python CLI. A live Blender MCP connection is not configured or claimed. New recipe construction and export can later be invoked through a verified MCP integration.
