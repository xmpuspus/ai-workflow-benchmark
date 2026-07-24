"""drift command - regression watch between a fresh run and a reference baseline."""

from __future__ import annotations

import json
import sys

import click
from rich.table import Table

from awb.analysis.drift import compute_drift, load_reference
from awb.commands._shared import (
    BAD,
    INFO,
    MUTED,
    OK,
    WARN,
    console,
    emit_json,
    headline_panel,
    resolve_run_dir_or_exit,
    score_style,
)


@click.command()
@click.argument("run_dir", required=False, type=click.Path())
@click.option(
    "--baseline",
    "baseline_path",
    required=True,
    type=click.Path(exists=True),
    help="Reference to compare against: a prior run directory or an awb/v2 baseline JSON file.",
)
@click.option(
    "--threshold",
    type=float,
    default=5.0,
    show_default=True,
    help="Mean composite score drop (points) beyond which the run is flagged as drifted.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the DriftReport as a JSON document on stdout.",
)
def drift(run_dir: str | None, baseline_path: str, threshold: float, fmt: str):
    """Compare a fresh run against a reference and flag regressions.

    RUN_DIR defaults to the most recently saved run (see --last-run plumbing
    in _shared.py) when omitted, or when passed the literal "last".

    Exit code contract: exits 1 when the composite has drifted past --threshold
    (in both --format text and --format json), exits 2 when run_dir is omitted
    and no run has been saved, or when an explicit run_dir doesn't exist,
    exits 0 otherwise. Intended for cron/CI regression watch - models and
    harnesses update silently.
    """
    resolved = resolve_run_dir_or_exit(run_dir, fmt)
    if (run_dir is None or run_dir == "last") and fmt == "text":
        console.print(f"[{MUTED}]using last run: {resolved}[/{MUTED}]")

    try:
        current = load_reference(resolved)
        reference = load_reference(baseline_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        # A run_dir that is actually a stray file, or a corrupt baseline JSON,
        # is a tool-failure input, not a drift verdict: exit 2 per the contract.
        if fmt == "json":
            click.echo(json.dumps({"error": f"could not load reference: {exc}"}))
        else:
            console.print(f"[{BAD}]Could not load reference: {exc}[/{BAD}]")
        sys.exit(2)

    if not current.per_task or not reference.per_task:
        # Keep json-mode stdout a single parseable document even on the
        # empty-input error path; cron/CI consumers parse it.
        if fmt == "json":
            click.echo(json.dumps({"error": "no results found in run dir or baseline"}))
        else:
            console.print(f"[{BAD}]No results found in run dir or baseline[/{BAD}]")
        sys.exit(1)

    report = compute_drift(current, reference, threshold)

    if fmt == "json":
        emit_json(report)
        sys.exit(1 if report.drifted else 0)

    verdict = f"[{BAD}]DRIFT[/{BAD}]" if report.drifted else f"[{OK}]OK[/{OK}]"
    delta_style = BAD if report.delta < 0 else OK
    console.print(
        headline_panel(
            "Composite Drift",
            f"{report.mean_reference:.1f} -> {report.mean_current:.1f}  "
            f"([{delta_style}]{report.delta:+.1f}[/{delta_style}])  {verdict}",
            subtitle=f"{reference.label} -> {current.label}  threshold=-{threshold:.1f}",
        )
    )

    if report.task_set_hash_mismatch:
        console.print(
            f"[{WARN}]Task set hash mismatch between current run and reference - "
            f"the task set may have changed since the reference was recorded[/{WARN}]"
        )
    if report.new_tasks:
        console.print(f"[{INFO}]New tasks not in reference:[/{INFO}] {', '.join(report.new_tasks)}")
    if report.missing_tasks:
        console.print(
            f"[{WARN}]Tasks missing from current run:[/{WARN}] {', '.join(report.missing_tasks)}"
        )

    if report.regressions:
        table = Table(title="Regressions (worst first)", header_style="bold")
        table.add_column("Task")
        table.add_column("Reference", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Delta", justify="right")
        for r in report.regressions:
            style = score_style(r.cur_score)
            table.add_row(
                r.task_id,
                f"{r.ref_score:.0f}",
                f"[{style}]{r.cur_score:.0f}[/{style}]",
                f"[{BAD}]{r.delta:.0f}[/{BAD}]",
            )
        console.print(table)
    else:
        console.print(f"\n[{MUTED}]No task-level regressions[/{MUTED}]")

    sys.exit(1 if report.drifted else 0)
