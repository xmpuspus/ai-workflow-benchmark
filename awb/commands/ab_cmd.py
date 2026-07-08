"""ab command - paired config A/B testing for the same adapter.

Runs one adapter twice over the same tasks, once per config directory (e.g.
two CLAUDE.md/settings setups), then reports per-task deltas and a paired
sign test. Answers "I changed my CLAUDE.md - did it help?".
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import (
    BAD,
    MUTED,
    OK,
    WARN,
    console,
    emit_json,
    headline_panel,
    score_style,
)


def _resolve_adapter_class(tool: str) -> type:
    """Validate the tool name and confirm it supports config-dir overrides."""
    from awb.adapters.registry import get_adapter as _get_adapter

    try:
        instance = _get_adapter(tool)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    if not getattr(instance, "supports_config_dir", False):
        raise click.UsageError(
            f"Adapter '{tool}' does not support --config-a/--config-b. "
            "Only claude-code-custom supports config directory overrides today."
        )
    return type(instance)


def _run_config(tool: str, adapter, tasks, run_id: str, timeout, runs_dir: Path):
    from awb.core.results import ResultRecorder
    from awb.core.runner import BenchmarkRunner

    runner = BenchmarkRunner(tool=tool, tasks=tasks, runs=1, timeout_override=timeout)
    # Inject the config-pinned adapter instance the runner would otherwise
    # build itself from the bare tool name (same override pattern the test
    # suite already uses - see tests/test_runner_trace.py).
    runner._adapter = adapter
    runner.recorder = ResultRecorder(results_dir=runs_dir)
    runner._run_id = run_id
    return asyncio.run(runner.run_all())


def _render(report) -> None:
    sign = "+" if report.mean_delta >= 0 else ""
    color = OK if report.mean_delta > 0 else (BAD if report.mean_delta < 0 else MUTED)
    p_str = f"p={report.p_value:.3f}" if report.p_value is not None else "n/a"

    if report.n_tasks == 0:
        verdict = "no shared tasks between the two configs"
    elif report.p_value is None:
        # The sign test needs 5+ pairs; "no significant difference" would
        # misread as a tested null result.
        verdict = report.message
    elif not report.significant:
        verdict = "no significant difference"
    elif report.mean_delta > 0:
        verdict = "config B improves over config A"
    else:
        verdict = "config B hurts relative to config A"

    console.print(
        headline_panel(
            "Config A/B Delta",
            f"[{color}]{sign}{report.mean_delta:.1f} pts[/{color}]",
            f"{p_str}  ({report.n_tasks} shared tasks)  {verdict}",
        )
    )
    console.print(f"  {report.message}")

    if report.per_task:
        table = Table(title="Per-Task Scores", header_style="bold")
        table.add_column("Task")
        table.add_column("Config A", justify="right")
        table.add_column("Config B", justify="right")
        table.add_column("Delta", justify="right")
        for d in report.per_task:
            style_a = score_style(d.score_a)
            style_b = score_style(d.score_b)
            delta_style = OK if d.delta > 0 else (BAD if d.delta < 0 else MUTED)
            delta_sign = "+" if d.delta > 0 else ""
            table.add_row(
                d.task_id,
                f"[{style_a}]{d.score_a:.0f}[/{style_a}]",
                f"[{style_b}]{d.score_b:.0f}[/{style_b}]",
                f"[{delta_style}]{delta_sign}{d.delta:.0f}[/{delta_style}]",
            )
        console.print(table)

    console.print(
        f"\n[{MUTED}]Config A hash: {report.config_hash_a}  "
        f"Config B hash: {report.config_hash_b}[/{MUTED}]"
    )


@click.command()
@click.argument("tool")
@click.option(
    "--config-a",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Config directory for the baseline (e.g. a CLAUDE_CONFIG_DIR copy).",
)
@click.option(
    "--config-b",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Config directory for the variant being tested.",
)
@click.option("--category", help="Filter tasks by category")
@click.option("--task", "task_ids", multiple=True, help="Run only this task ID (repeatable)")
@click.option("--timeout", type=int, help="Override timeout (seconds) for both configs")
@click.option("--max-turns", type=int, help="Override max iterations for both configs")
@click.option(
    "--runs-dir",
    default="results/runs",
    show_default=True,
    help="Directory to write run results under",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the ABReport as a JSON document on stdout.",
)
def ab(
    tool: str,
    config_a: str,
    config_b: str,
    category: str | None,
    task_ids: tuple[str, ...],
    timeout: int | None,
    max_turns: int | None,
    runs_dir: str,
    fmt: str,
):
    """Run TOOL twice, once per config dir, and compare per-task scores."""
    from awb.core.task_loader import load_all_tasks
    from awb.scoring.ab import build_ab_report

    adapter_cls = _resolve_adapter_class(tool)

    tasks = load_all_tasks(category=category)
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in tasks if t.id in wanted]
        missing = wanted - {t.id for t in tasks}
        if missing:
            console.print(f"[{BAD}]Task(s) not found: {', '.join(sorted(missing))}[/{BAD}]")
            sys.exit(1)

    if not tasks:
        console.print(f"[{WARN}]No tasks matched filters[/{WARN}]")
        return

    if max_turns:
        tasks = [
            dataclasses.replace(
                t, constraints=dataclasses.replace(t.constraints, max_iterations=max_turns)
            )
            for t in tasks
        ]

    adapter_a = adapter_cls(config_dir=Path(config_a))
    adapter_b = adapter_cls(config_dir=Path(config_b))

    # Check both up front: a broken config B discovered only after the full
    # config A pass wastes the entire A run.
    for label, adapter in (("A", adapter_a), ("B", adapter_b)):
        if not adapter.check_available():
            console.print(f"[{BAD}]Adapter '{tool}' is not available for config {label}[/{BAD}]")
            sys.exit(1)

    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    runs_dir_path = Path(runs_dir)

    # Progress lines are text-mode only so `--format json` stdout stays
    # parseable as a single JSON document.
    if fmt == "text":
        console.print(
            f"Running [bold]{tool}[/bold] with config A ({config_a}) on {len(tasks)} task(s)"
        )
    results_a = _run_config(tool, adapter_a, tasks, f"{ts}_ab_a", timeout, runs_dir_path)

    if fmt == "text":
        console.print(
            f"Running [bold]{tool}[/bold] with config B ({config_b}) on {len(tasks)} task(s)"
        )
    results_b = _run_config(tool, adapter_b, tasks, f"{ts}_ab_b", timeout, runs_dir_path)

    report = build_ab_report(
        results_a,
        results_b,
        label_a=config_a,
        label_b=config_b,
        config_hash_a=adapter_a.get_config_hash(),
        config_hash_b=adapter_b.get_config_hash(),
    )

    if fmt == "json":
        emit_json(report)
        return

    _render(report)
