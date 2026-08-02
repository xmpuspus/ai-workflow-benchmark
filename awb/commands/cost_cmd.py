"""cost command - cost-per-solved-task report, grouped by tool."""

from __future__ import annotations

import sys
from pathlib import Path

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
    resolve_run_dir_or_exit,
)


@click.command()
@click.argument("run_dirs", nargs=-1, type=click.Path())
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the list of CostReport as a JSON document on stdout.",
)
def cost(run_dirs: tuple[str, ...], fmt: str):
    """Report cost-per-solved-task, grouped by tool, cheapest-per-solved first.

    RUN_DIRS defaults to the most recently saved run (see --last-run
    plumbing in _shared.py) when omitted, or when passed the literal "last".
    """
    if not run_dirs or run_dirs == ("last",):
        resolved = resolve_run_dir_or_exit(None, fmt)
        if fmt == "text":
            console.print(f"[{MUTED}]using last run: {resolved}[/{MUTED}]")
        run_dirs = (str(resolved),)
    else:
        missing = [d for d in run_dirs if not Path(d).exists()]
        if missing:
            message = f"Run directory not found: {missing[0]}"
            if fmt == "json":
                emit_json({"error": message[0].lower() + message[1:]})
            else:
                console.print(f"[{BAD}]{message}[/{BAD}]")
            sys.exit(2)

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
                (
                    f"{cheapest.tool}  {cheapest.credits_per_solved:.2f} credits "
                    f"(${cheapest.cost_per_solved:.2f} equivalent)"
                    if cheapest.credits_per_solved is not None
                    else f"{cheapest.tool}  ${cheapest.cost_per_solved:.2f}"
                ),
                subtitle=f"{cheapest.n_solved}/{cheapest.n_tasks} solved",
            )
        )
    else:
        console.print(
            f"[{WARN}]No tool solved any task - no cost-per-solved figure available[/{WARN}]"
        )

    table = Table(title="Cost per Tool", header_style="bold")
    table.add_column("Tool")
    table.add_column("Solved", justify="right")
    table.add_column("Total Cost", justify="right")
    table.add_column("$/Solved", justify="right")
    table.add_column("Wasted", justify="right")
    table.add_column("Credits", justify="right")
    table.add_column("Cr/Solved", justify="right")
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
            (
                f"{r.total_credits:.2f}"
                if r.total_credits is not None
                else f"[{MUTED}]n/a[/{MUTED}]"
            ),
            (
                f"{r.credits_per_solved:.2f}"
                if r.credits_per_solved is not None
                else f"[{MUTED}]n/a[/{MUTED}]"
            ),
            tokens_str,
        )
    console.print(table)
