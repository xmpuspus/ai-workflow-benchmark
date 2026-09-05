"""Render a saved benchmark run without triggering model or auth activity."""

from __future__ import annotations

from pathlib import Path

import click

from awb.commands._shared import emit_json, resolve_run_dir_or_exit
from awb.presentation.report import build_report, render_html, render_text


@click.command()
@click.argument("run_dir", required=False, default="last")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "html"]), default="text")
@click.option(
    "--output", type=click.Path(), help="HTML output path (defaults inside the run directory)."
)
def report(run_dir: str, fmt: str, output: str | None) -> None:
    """Summarize saved evidence. This command never executes a model or adapter."""
    path = resolve_run_dir_or_exit(run_dir, fmt)
    payload = build_report(path)
    if fmt == "json":
        emit_json(payload)
        return
    if fmt == "html":
        out = Path(output) if output else path / "awb-report.html"
        out.write_text(render_html(payload))
        click.echo(str(out))
        return
    click.echo(render_text(payload))
