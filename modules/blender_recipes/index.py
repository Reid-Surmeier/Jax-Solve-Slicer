"""PROTOTYPE: Blender CLI entry point; use -- after Blender arguments."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from modules.blender_recipes.prototype import main

if __name__ == "__main__":
    main()
