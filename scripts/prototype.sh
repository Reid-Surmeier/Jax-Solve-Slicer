#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
blender_executable="${BLENDER:-$HOME/.local/opt/blender-4.3.2/blender}"
alpha_folder="${1:-docs/reproduction/2026-09-20/alpha}"
output_folder="${2:-outputs/blender-prototype}"
"$blender_executable" -b --factory-startup --python-exit-code 1 --python modules/blender_recipes/index.py -- "$alpha_folder" "$output_folder"
.venv/bin/python modules/blender_recipes/mixbox_preview.py "$alpha_folder" "$output_folder"
for recipe in hatch curve stamp stamp-wide-spacing; do
    rsvg-convert -w 720 -o "$output_folder/$recipe.png" "$output_folder/$recipe.svg"
done
python3 scripts/prototype_gallery.py "$output_folder"
