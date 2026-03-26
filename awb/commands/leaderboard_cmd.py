"""leaderboard command — generate HTML leaderboard."""
from __future__ import annotations

from pathlib import Path

import click

from awb.commands._shared import console


@click.command()
@click.option("--output-dir", type=click.Path(), help="Output directory")
def leaderboard(output_dir: str | None):
    """Generate HTML leaderboard from results."""
    from awb.leaderboard.generate import generate_leaderboard

    out = Path(output_dir) if output_dir else None
    path = generate_leaderboard(output_dir=out)
    console.print(f"Leaderboard generated: [bold]{path}[/bold]")
