from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def portable_artifact_path(path: Path, *, output_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(output_root.resolve())
    except ValueError as error:
        raise ValueError(
            f"generated artifact is outside its output root: {path.name}"
        ) from error
    return relative.as_posix()
