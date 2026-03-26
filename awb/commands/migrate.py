"""Migrate v0.5.x results to v1.0 format."""
from __future__ import annotations

import json
from pathlib import Path

import click

from awb.commands._shared import console


@click.command("migrate-results")
@click.argument("old_dir", type=click.Path(exists=True))
@click.option("--output", "-o", "output_dir", type=click.Path(), help="Output directory (default: in-place)")  # noqa: E501
def migrate_results(old_dir: str, output_dir: str | None):
    """Migrate v0.5.x result JSON files to v1.0 format."""
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

        if data.get("version") == "1.0":
            continue

        original = dict(data)
        data["version"] = "1.0"
        data["_v05x_original"] = original
        data.setdefault("hardware", None)
        data.setdefault("adapter_config_hash", None)

        out_file = out_path / f.relative_to(old_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as fh:
            json.dump(data, fh, indent=2)
        migrated += 1

    console.print(f"Migrated {migrated} file(s) to v1.0 format")
