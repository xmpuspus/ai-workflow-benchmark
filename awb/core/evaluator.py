"""Deterministic identity for the packaged AWB evaluator source."""

from __future__ import annotations

import hashlib
from pathlib import Path


def package_source_fingerprint(package_root: Path | None = None) -> str:
    """Hash each packaged Python source path and its bytes in stable order."""
    root = package_root or Path(__file__).resolve().parents[1]
    hasher = hashlib.sha256()
    paths = sorted(root.rglob("*.py"), key=lambda path: path.relative_to(root).as_posix())
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Packaged evaluator source is not a regular file: {path}")
        relative = path.relative_to(root).as_posix().encode()
        hasher.update(relative)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def evaluator_identity(package_version: str, package_root: Path | None = None) -> str:
    """Return the human package version with its exact packaged source digest."""
    return f"{package_version}+source.{package_source_fingerprint(package_root)}"
