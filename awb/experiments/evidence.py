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
    root = root.absolute()
    path = path.absolute()
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Evidence artifact must be inside the run directory") from exc
    if not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("Unsafe evidence artifact path")
    if any(part.lower() in _FORBIDDEN for part in rel.parts):
        raise ValueError("Credential or state artifact is not permitted")
    cursor = root
    for part in rel.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("Evidence artifact path contains a symlink")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError("Evidence artifact must resolve inside the run directory") from exc
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


def _artifact_kind(name: str) -> str | None:
    path = PurePosixPath(name)
    if path.parts[0] == "metadata":
        return "metadata" if len(path.parts) == 2 and path.name in _METADATA else None
    if path.parts[0] == "attachments":
        return "attachment" if path.suffix in _ATTACHMENT_SUFFIXES else None
    return "result" if _RESULT.fullmatch(path.name) else None


def verify_bundle(directory: Path) -> list[str]:
    """Check manifest structure, checksums, and exact recursive contents."""
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Bundle directory does not exist or is a symlink")
    root = directory.resolve()
    path = root / "manifest.json"
    if path.is_symlink():
        raise ValueError("Manifest symlink is not permitted")
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError("Bundle manifest must be an object")
    files = manifest.get("files")
    metadata = manifest.get("metadata")
    if manifest.get("schema_version") != 2 or not isinstance(files, dict):
        raise ValueError("Unsupported bundle manifest")
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("complete"), bool)
        or not isinstance(metadata.get("artifacts"), dict)
    ):
        raise ValueError("Invalid bundle metadata")
    errors = []
    kinds: dict[str, str] = {}
    for name, expected in files.items():
        if (
            not isinstance(name, str)
            or not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or not _safe_name(name)
        ):
            errors.append(f"Unsafe manifest artifact: {name}")
            continue
        kind = _artifact_kind(name)
        if kind is None:
            errors.append(f"Unsupported manifest artifact: {name}")
            continue
        kinds[name] = kind
        artifact = root / name
        try:
            _, payload = _read(artifact, root)
        except ValueError:
            errors.append(f"Missing, outside-root, or symlink artifact: {name}")
            continue
        if _digest(payload) != expected:
            errors.append(f"Checksum mismatch: {name}")
            continue
        if kind == "result":
            try:
                result = json.loads(payload)
            except json.JSONDecodeError:
                result = None
            if not isinstance(result, dict) or not result.get("task_id"):
                errors.append(f"Invalid result artifact: {name}")

    metadata_entries = metadata["artifacts"]
    complete_metadata = True
    for filename, metadata_kind in _METADATA.items():
        expected_path = f"metadata/{filename}"
        entry = metadata_entries.get(metadata_kind)
        valid = (
            isinstance(entry, dict)
            and entry.get("path") == expected_path
            and entry.get("sha256") == files.get(expected_path)
            and kinds.get(expected_path) == "metadata"
        )
        complete_metadata = complete_metadata and valid
        if entry is not None and not valid:
            errors.append(f"Invalid metadata declaration: {metadata_kind}")
    if set(metadata_entries) - set(_METADATA.values()):
        errors.append("Bundle declares unknown metadata")
    if metadata["complete"] != complete_metadata:
        errors.append("Bundle metadata completeness is inconsistent")
    actual = set()
    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()
        if item.is_symlink():
            errors.append(f"Bundle contains symlink: {relative}")
        elif item.is_file() and item != path:
            actual.add(relative)
    if actual != set(files):
        errors.append("Bundle contains missing or unlisted files")
    if "result" not in kinds.values():
        errors.append("Bundle contains no result artifacts")
    return errors
