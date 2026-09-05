"""Portable declared experiment evidence bundles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

_RESULT = re.compile(r"^[A-Z]{2}-[0-9]{3}.*\.json$")
_METADATA = {
    "plan.json": "frozen_plan",
    "evaluator.json": "evaluator",
    "environment.json": "environment",
}
_ATTACHMENT_SUFFIXES = {".jsonl", ".patch", ".diff"}
_FORBIDDEN = {"auth.json", "credentials.json", "sessions", "state", "history.jsonl"}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative(path: Path, root: Path) -> Path:
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Evidence artifact must be inside the run directory") from exc
    if not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("Unsafe evidence artifact path")
    if any(part.lower() in _FORBIDDEN for part in rel.parts):
        raise ValueError("Credential or state artifact is not permitted")
    return rel


def _read(path: Path, root: Path) -> tuple[Path, bytes]:
    rel = _relative(path, root)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Evidence symlink or non-file is not permitted: {rel}")
    return rel, path.read_bytes()


def _add(files: dict[str, bytes], name: str, payload: bytes) -> None:
    if name in files:
        raise ValueError(f"Duplicate evidence artifact: {name}")
    files[name] = payload


def build_bundle(
    run_dir: Path, destination: Path, *, attachments: list[Path] | None = None
) -> dict:
    """Copy nested result receipts, declared replay metadata, and selected attachments."""
    if destination.exists():
        raise ValueError("Bundle destination already exists")
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ValueError("Run directory does not exist or is a symlink")
    root = run_dir.resolve()
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*.json")):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part.lower() in _FORBIDDEN for part in rel.parts) or not _RESULT.fullmatch(
            path.name
        ):
            continue
        _, payload = _read(path, root)
        data = json.loads(payload)
        if not isinstance(data, dict) or not data.get("task_id"):
            raise ValueError(f"Not a result: {rel}")
        _add(files, rel.as_posix(), payload)
    if not files:
        raise ValueError("No task results to export")

    metadata: dict[str, dict[str, str]] = {}
    for filename, kind in _METADATA.items():
        path = root / filename
        if not path.exists():
            continue
        rel, payload = _read(path, root)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Metadata is not JSON: {rel}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Metadata is not an object: {rel}")
        name = f"metadata/{filename}"
        _add(files, name, payload)
        metadata[kind] = {"path": name, "sha256": _digest(payload)}

    for attachment in attachments or []:
        rel, payload = _read(Path(attachment), root)
        if rel.suffix not in _ATTACHMENT_SUFFIXES:
            raise ValueError("Attachment must be a trace JSONL, patch, or diff")
        _add(files, f"attachments/{rel.as_posix()}", payload)

    manifest = {
        "schema_version": 2,
        "contents": "declared_results_metadata_and_attachments",
        "privacy": {
            "results": "Result fields may contain private metadata. Review before sharing.",
            "attachments": "explicitly selected; review before sharing",
        },
        "claim": "Checksums establish identity, not benchmark validity or replay success.",
        "metadata": {"complete": len(metadata) == len(_METADATA), "artifacts": metadata},
        "files": {name: _digest(payload) for name, payload in sorted(files.items())},
    }
    destination.mkdir(parents=True)
    for name, payload in files.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def verify_bundle(directory: Path) -> list[str]:
    """Check manifest structure, checksums, and exact recursive contents."""
    path = directory / "manifest.json"
    if path.is_symlink():
        raise ValueError("Manifest symlink is not permitted")
    manifest = json.loads(path.read_text())
    files = manifest.get("files") if isinstance(manifest, dict) else None
    metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
    if manifest.get("schema_version") != 2 or not isinstance(files, dict):
        raise ValueError("Unsupported bundle manifest")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("complete"), bool):
        raise ValueError("Invalid bundle metadata")
    errors = []
    for name, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64 or not _safe_name(name):
            errors.append(f"Unsafe manifest artifact: {name}")
            continue
        artifact = directory / name
        if artifact.is_symlink() or not artifact.is_file():
            errors.append(f"Missing or symlink artifact: {name}")
        elif _digest(artifact.read_bytes()) != expected:
            errors.append(f"Checksum mismatch: {name}")
    actual = {
        item.relative_to(directory).as_posix()
        for item in directory.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    if actual != set(files):
        errors.append("Bundle contains missing or unlisted files")
    if not files:
        errors.append("Bundle contains no results")
    return errors
