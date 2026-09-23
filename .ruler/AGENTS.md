# Jax Solve Slicer

Read the active GitHub issue, `MODULES.md`, and `CONTEXT.md` before changing the pipeline. The map is https://github.com/Reid-Surmeier/Jax-Solve-Slicer/issues/1.

## Prototype scope

The owner accepted the reproduced reference and authorized porting the Python stages and exploring Blender, Mixbox, and editable SVG recipes. Preserve the verified RGB baseline. Label prototypes and distinguish alpha reconstruction, SVG rendering, and physical paint predictions.

Blender requires Python through `bpy`; existing stages are also Python. This is the new-repo skill's host-language exception. Keep the template's generated map, testing/review modules, project sets, and generated instructions. No speculative TypeScript wrapper is needed for this prototype.

## Modules and source custody

Read each module's `MODULE.md` for its interface and acceptance checks. Production interfaces, errors and acceptance tests are frozen after specification; prototype interfaces are explicitly provisional under the prototype issue. Ported legacy files retain their source hashes and provenance. Modify recipes through Blender node groups and exposed controls; SVG export must serialize evaluated geometry in declared units.

`repos/` is read-only upstream reference, never an import path. Installed packages supply runtime dependencies. Pin imported source and record versions. Use the official `pymixbox` distribution (import `mixbox`); the unrelated `mixbox` PyPI distribution is not the pigment library.

## Work and verification

Work on `build/0.1.0` and its single build PR. Main advances only through the release workflow after initialization. The prototype is not a release. Every visible change includes actual rendered output in the PR. Run `npm run check`; run Blender acceptance checks when node graphs or export behavior change.

Edit these instructions in `.ruler/AGENTS.md`, then run `npm run gates:apply`. Root `AGENTS.md` and `CLAUDE.md` are generated. Configure tools through `project-sets.json` and `npm run sets:apply`. A host Blender binary is not proof of a working Blender MCP connection.

Use GitHub as `Reid-Surmeier`; secrets go through the Bitwarden runner. The current valid token is `GITHUB_TOKEN`. Keep source images, manifests, and generated files free of secrets and temporary machine paths. Paid generation is unnecessary for the prototype.

<!-- gitnexus:start — written by scripts/project_sets.py from project-sets.json -->
## GitNexus

This repository is indexed by GitNexus: use it to find your way in unfamiliar code, and check with it before renaming, deleting or moving something other code depends on. `node .gitnexus/run.cjs analyze --index-only` refreshes the index.
<!-- gitnexus:end -->
