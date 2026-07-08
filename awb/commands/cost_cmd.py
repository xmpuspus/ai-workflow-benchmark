"""cost command — cost-per-solved-task report, grouped by tool."""

from __future__ import annotations

import sys

import click
from rich.table import Table

from awb.analysis.cost import build_cost_report
from awb.commands._shared import (
    BAD,
    MUTED,
    WARN,
    console,
    emit_json,
    headline_panel,
    load_results_from_dirs,
)


@click.command()
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the list of CostReport as a JSON document on stdout.",
)
def cost(run_dirs: tuple[str, ...], fmt: str):
    """Report cost-per-solved-task, grouped by tool, cheapest-per-solved first."""
    results = load_results_from_dirs(run_dirs)
    if not results:
        console.print(f"[{BAD}]No results found[/{BAD}]")
        sys.exit(1)

    reports = build_cost_report(results)

    if fmt == "json":
        emit_json(reports)
        return

    cheapest = next((r for r in reports if r.cost_per_solved is not None), None)
    if cheapest is not None:
        console.print(
            headline_panel(
                "Cheapest per Solved Task",
                f"{cheapest.tool}  ${cheapest.cost_per_solved:.2f}",
                subtitle=f"{cheapest.n_solved}/{cheapest.n_tasks} solved",
            )
        )
    else:
        console.print(
            f"[{WARN}]No tool solved any task — no cost-per-solved figure available[/{WARN}]"
        )

    table = Table(title="Cost per Tool", header_style="bold")
    table.add_column("Tool")
    table.add_column("Solved", justify="right")
    table.add_column("Total Cost", justify="right")
    table.add_column("$/Solved", justify="right")
    table.add_column("Wasted", justify="right")
    table.add_column("Tokens/Solved", justify="right")
    for r in reports:
        solved_str = f"{r.n_solved}/{r.n_tasks}"
        cost_per_solved_str = (
            f"${r.cost_per_solved:.2f}"
            if r.cost_per_solved is not None
            else f"[{MUTED}]n/a[/{MUTED}]"
        )
        tokens_str = (
            f"{r.tokens_per_solved:,.0f}"
            if r.tokens_per_solved is not None
            else f"[{MUTED}]n/a[/{MUTED}]"
        )
        table.add_row(
            r.tool,
            solved_str,
            f"${r.total_cost_usd:.2f}",
            cost_per_solved_str,
            f"${r.wasted_cost_usd:.2f}",
            tokens_str,
        )
    console.print(table)
