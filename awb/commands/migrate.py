"""Migrate older result JSON formats to the current schema (v2)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from awb.commands._shared import console


def _migrate_one(data: dict) -> dict:
    """Bring a single result dict up to schema_version=2.

    Pipeline: v0.5.x -> v1.0 -> v2. Idempotent on already-v2 data.
    """
    # Already current?
    if data.get("schema_version") == 2:
        return data

    # v0.5.x -> v1.0 (preserve original under _v05x_original on first migration)
    if data.get("version") != "1.0" and data.get("schema_version") is None:
        original = dict(data)
        data["version"] = "1.0"
        data["_v05x_original"] = original
        data.setdefault("hardware", None)
        data.setdefault("adapter_config_hash", None)

    # v1.0 -> v2
    data["schema_version"] = 2
    # task_set_hash is required in v2; use a sentinel zero-hash for legacy
    # records since we cannot recover the actual task set state in retrospect.
    data.setdefault("task_set_hash", "0" * 64)
    data.setdefault("trace_path", "")
    return data


@click.command("migrate-results")
@click.argument("old_dir", type=click.Path(exists=True))
@click.option(
    "--output", "-o", "output_dir", type=click.Path(), help="Output directory (default: in-place)"
)  # noqa: E501
def migrate_results(old_dir: str, output_dir: str | None):
    """Migrate older result JSON files to current schema (v2)."""
    old_path = Path(old_dir)
    out_path = Path(output_dir) if output_dir else old_path
    out_path.mkdir(parents=True, exist_ok=True)

    files = list(old_path.rglob("*.json"))
    if not files:
        console.print("[yellow]No JSON files found[/yellow]")
        return

    migrated = 0
    for f in files:
        with f.open() as fh:
            data = json.load(fh)

        if data.get("schema_version") == 2:
            continue

        data = _migrate_one(data)

        out_file = out_path / f.relative_to(old_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as fh:
            json.dump(data, fh, indent=2)
        migrated += 1

    console.print(f"Migrated {migrated} file(s) to schema_version=2")
