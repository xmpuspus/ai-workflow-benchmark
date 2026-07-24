"""`awb trace grade <run_dir>` — score trace artifacts by 4 behaviors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from awb.commands._shared import BAD, MUTED, console, resolve_run_dir
from awb.trace.grader import grade_trace


@click.group()
def trace():
    """Inspect and grade trace artifacts."""


@trace.command("grade")
@click.argument("run_dir", required=False, type=click.Path())
def grade(run_dir: str | None):
    """Score every trace.jsonl in RUN_DIR by 4 behavior dimensions (0-100).

    RUN_DIR defaults to the most recently saved run (see --last-run plumbing
    in _shared.py) when omitted, or when passed the literal "last".
    """
    resolved = resolve_run_dir(run_dir)
    if resolved is None:
        console.print(f"[{BAD}]No run directory given and no last run saved[/{BAD}]")
        sys.exit(2)
    if run_dir is None or run_dir == "last":
        console.print(f"[{MUTED}]using last run: {resolved}[/{MUTED}]")

    run_dir = Path(resolved)
    trace_files = sorted(run_dir.glob("*.trace.jsonl"))
    if not trace_files:
        console.print("[yellow]No .trace.jsonl files found[/yellow]")
        return

    rows: list[tuple[str, dict[str, int]]] = []
    for tp in trace_files:
        # Best-effort: pull files_to_examine from the matching result.json
        result_path = tp.with_name(tp.name.replace(".trace.jsonl", ".json"))
        files_to_examine: list[str] = []
        if result_path.exists():
            try:
                data = json.loads(result_path.read_text())
                files_to_examine = (data.get("task") or {}).get("files_to_examine") or []
            except (OSError, json.JSONDecodeError):
                files_to_examine = []
        scores = grade_trace(tp, files_to_examine=files_to_examine)
        rows.append((tp.stem.replace(".trace", ""), scores))

    console.print("\n[bold]Trace Behavior Scores[/bold] (0-100)\n")
    header = f"  {'task':<28} {'read_tests':>10} {'ran_verif':>9} {'in_scope':>8} {'no_loop':>7}"
    console.print(header)
    console.print(f"  {'-' * 28} {'-' * 10} {'-' * 9} {'-' * 8} {'-' * 7}")
    for name, sc in rows:
        console.print(
            f"  {name[:28]:<28} "
            f"{sc['read_tests_before_edit']:>10} "
            f"{sc['ran_verification_after_change']:>9} "
            f"{sc['no_out_of_scope_edits']:>8} "
            f"{sc['no_repeated_failing_command_loop']:>7}"
        )
