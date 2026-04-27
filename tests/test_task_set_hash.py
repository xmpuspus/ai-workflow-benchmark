"""Tests for compute_task_set_hash — determinism + change-detection."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from awb.scoring.integrity import compute_task_set_hash


def _write(tmp: Path, name: str, body: dict) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(body))
    return p


def test_returns_64_char_sha256_hex(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001"})
    h = compute_task_set_hash(tmp_path)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_deterministic_across_calls(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001"})
    _write(tmp_path, "b.yaml", {"id": "BF-002"})
    h1 = compute_task_set_hash(tmp_path)
    h2 = compute_task_set_hash(tmp_path)
    assert h1 == h2


def test_independent_of_creation_order(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001"})
    _write(tmp_path, "b.yaml", {"id": "BF-002"})
    h_first = compute_task_set_hash(tmp_path)
    # Touch in reverse order to perturb st_mtime
    os.utime(tmp_path / "b.yaml", None)
    os.utime(tmp_path / "a.yaml", None)
    h_after = compute_task_set_hash(tmp_path)
    assert h_first == h_after


def test_changes_when_content_changes(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001", "title": "v1"})
    h1 = compute_task_set_hash(tmp_path)
    _write(tmp_path, "a.yaml", {"id": "BF-001", "title": "v2"})
    h2 = compute_task_set_hash(tmp_path)
    assert h1 != h2


def test_changes_when_task_added(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001"})
    h1 = compute_task_set_hash(tmp_path)
    _write(tmp_path, "b.yaml", {"id": "BF-002"})
    h2 = compute_task_set_hash(tmp_path)
    assert h1 != h2


def test_skips_underscore_prefixed_files(tmp_path: Path):
    _write(tmp_path, "a.yaml", {"id": "BF-001"})
    h_only_a = compute_task_set_hash(tmp_path)
    _write(tmp_path, "_template.yaml", {"id": "TEMPLATE"})
    h_with_template = compute_task_set_hash(tmp_path)
    assert h_only_a == h_with_template


def test_real_bundled_tasks_dir_hashes_cleanly():
    """Sanity check: the actual 100 bundled task YAMLs hash to a stable value."""
    from awb.core.config import TASKS_DIR

    h = compute_task_set_hash(Path(str(TASKS_DIR)))
    assert len(h) == 64
    # Re-run to ensure the bundled set itself is deterministic
    assert h == compute_task_set_hash(Path(str(TASKS_DIR)))
