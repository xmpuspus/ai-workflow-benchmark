"""Explicit result-only exports. Hashes prove identity, not validity."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_RESULT = re.compile(r"^[A-Z]{2}-[0-9]{3}.*\.json$")


def build_bundle(run_dir: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Bundle destination already exists")
    if not run_dir.is_dir():
        raise ValueError("Run directory does not exist")
    files = {}
    for path in sorted(run_dir.glob("*.json")):
        if not _RESULT.fullmatch(path.name):
            continue
        if path.is_symlink():
            raise ValueError("Result symlink is not permitted")
        payload = path.read_bytes()
        data = json.loads(payload)
        if not isinstance(data, dict) or not data.get("task_id"):
            raise ValueError(f"Not a result: {path.name}")
        files[path.name] = payload
    if not files:
        raise ValueError("No task results to export")
    manifest = {
        "schema_version": 1,
        "contents": "results_only",
        "privacy": "Result fields may contain private metadata. Review before sharing.",
        "claim": "Checksums establish artifact identity, not benchmark validity.",
        "files": {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
    }
    destination.mkdir(parents=True)
    for name, payload in files.items():
        (destination / name).write_bytes(payload)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_bundle(directory: Path) -> list[str]:
    path = directory / "manifest.json"
    if path.is_symlink():
        raise ValueError("Manifest symlink is not permitted")
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported bundle manifest")
    errors = []
    for name, expected in manifest["files"].items():
        if not _RESULT.fullmatch(name) or Path(name).name != name:
            errors.append(f"Unsafe result name: {name}")
            continue
        result = directory / name
        if result.is_symlink() or not result.is_file():
            errors.append(f"Missing or symlink result: {name}")
        elif hashlib.sha256(result.read_bytes()).hexdigest() != expected:
            errors.append(f"Checksum mismatch: {name}")
    actual = {p.name for p in directory.iterdir()} - {"manifest.json"}
    if actual != set(manifest["files"]):
        errors.append("Bundle contains missing or unlisted files")
    if not manifest["files"]:
        errors.append("Bundle contains no results")
    return errors
