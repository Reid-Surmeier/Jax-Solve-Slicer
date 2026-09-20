"""Small portable acceptance gate; Blender checks run inside the prototype."""
import hashlib
import ast
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
entries = json.loads((root / "modules/legacy/provenance.json").read_text())
for entry in entries:
    assert hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest() == entry["sha256"], entry["path"]
for source in (root / "modules").rglob("*.py"):
    ast.parse(source.read_text(), filename=str(source))
for svg in (root / "outputs/blender-prototype").glob("*.svg"):
    tree = ET.parse(svg)
    assert tree.getroot().get("width", "").endswith("mm"), svg
    assert len(tree.findall(".//{http://www.w3.org/2000/svg}path")) > 0, svg
print(f"Legacy source custody: {len(entries)} files unchanged; available SVG outputs checked")
