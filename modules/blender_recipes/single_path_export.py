"""Export the current saved Blender curve as the flat one-path SVG; no graph rebuild."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from single_path_blender import export_svg_from_scene
print('EXPORTED_EDITED_CURVE',export_svg_from_scene())
