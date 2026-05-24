"""leaderboard command — generate HTML leaderboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from awb.commands._shared import INFO, MUTED, console, emit_json, score_style

# Named constants for the heuristic mapping from RunResult fields onto the
# 7 readiness dimensions. Extract so they're documented + tunable in one place.
REVIEW_BURDEN_FILES_TO_ZERO = 50.0  # ~50 modified files -> ~0 review-burden score
MAINTAINABILITY_LINT_TO_ZERO = 20.0  # 20+ new lint warnings -> ~0 maintainability
COST_USD_TO_ZERO = 5.0  # $5 per task -> ~0 cost score
SPEED_SECONDS_TO_ZERO = 1800.0  # 30 min -> ~0 speed score


@dataclass
class ToolReadiness:
    tool: str
    n_results: int
    composite: float
    correctness: float
    regression_safety: float
    security: float
    review_burden: float
    maintainability: float
    cost: float
    speed: float


@click.command()
@click.option("--output-dir", type=click.Path(), help="Output directory")
@click.option(
    "--readiness",
    is_flag=True,
    default=False,
    help="Print Production Readiness Score (0-100) per tool to stdout in addition to the HTML.",
)
@click.option(
    "--explain",
    is_flag=True,
    default=False,
    help="With --readiness, also print the 7 sub-scores per tool.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="With --readiness, switch output format. 'json' emits per-tool scores as JSON.",
)
def leaderboard(output_dir: str | None, readiness: bool, explain: bool, fmt: str):
    """Generate HTML leaderboard from results."""
    from awb.leaderboard.generate import generate_leaderboard

    out = Path(output_dir) if output_dir else None
    path = generate_leaderboard(output_dir=out)
    if fmt == "text":
        console.print(f"Leaderboard generated: [bold]{path}[/bold]")

    if readiness:
        scores = _compute_readiness_scores()
        if not scores:
            if fmt == "text":
                console.print("[yellow]No results found — readiness summary skipped.[/yellow]")
            return
        if fmt == "json":
            emit_json([s.__dict__ for s in scores])
        else:
            _render_readiness_panel(scores, explain=explain)


def _compute_readiness_scores() -> list[ToolReadiness]:
    from awb.core.results import ResultRecorder
    from awb.scoring.readiness import compute_readiness_score

    recorder = ResultRecorder()
    runs = recorder.load_all_runs()
    by_tool: dict[str, list] = {}
    for results in runs.values():
        for r in results:
            by_tool.setdefault(r.tool, []).append(r)
    out: list[ToolReadiness] = []
    for tool in sorted(by_tool):
        results = by_tool[tool]
        n = len(results) or 1

        def _mean(fn, _results=results, _n=n):
            return sum(fn(r) for r in _results) / _n

        correctness = 100.0 * sum(1 for r in results if r.outcome.success) / n
        regression_safety = 100.0 * sum(1 for r in results if r.quality.test_regressions == 0) / n
        security = 100.0 * sum(1 for r in results if r.quality.security_delta <= 0) / n
        review_burden = max(
            0.0,
            100.0 - 100.0 * _mean(lambda r: r.metrics.files_modified) / REVIEW_BURDEN_FILES_TO_ZERO,
        )
        maintainability = max(
            0.0,
            100.0
            - 100.0
            * max(0.0, _mean(lambda r: r.quality.lint_delta))
            / MAINTAINABILITY_LINT_TO_ZERO,
        )
        cost_score = max(
            0.0,
            100.0 - 100.0 * _mean(lambda r: r.cost.estimated_cost_usd) / COST_USD_TO_ZERO,
        )
        speed = max(
            0.0,
            100.0 - 100.0 * _mean(lambda r: r.metrics.wall_clock_seconds) / SPEED_SECONDS_TO_ZERO,
        )
        composite = compute_readiness_score(
            correctness=correctness,
            regression_safety=regression_safety,
            security=security,
            review_burden=review_burden,
            maintainability=maintainability,
            cost=cost_score,
            speed=speed,
        )
        out.append(
            ToolReadiness(
                tool=tool,
                n_results=n,
                composite=composite,
                correctness=correctness,
                regression_safety=regression_safety,
                security=security,
                review_burden=review_burden,
                maintainability=maintainability,
                cost=cost_score,
                speed=speed,
            )
        )
    out.sort(key=lambda s: -s.composite)
    return out


def _render_readiness_panel(scores: list[ToolReadiness], explain: bool) -> None:
    ranked = scores
    if not explain:
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("#", justify="right")
        table.add_column("Tool")
        table.add_column("Score", justify="right")
        table.add_column("n", justify="right")
        for i, s in enumerate(ranked, 1):
            style = score_style(s.composite)
            table.add_row(
                str(i),
                s.tool,
                f"[{style}]{s.composite:5.1f}[/{style}]",
                str(s.n_results),
            )
    else:
        table = Table(show_header=True, header_style="bold", box=None)
        for col, just in [
            ("#", "right"),
            ("Tool", "left"),
            ("Score", "right"),
            ("Correct", "right"),
            ("Regr-safe", "right"),
            ("Sec", "right"),
            ("Review", "right"),
            ("Maint", "right"),
            ("Cost", "right"),
            ("Speed", "right"),
            ("n", "right"),
        ]:
            table.add_column(col, justify=just)
        for i, s in enumerate(ranked, 1):
            style = score_style(s.composite)
            table.add_row(
                str(i),
                s.tool,
                f"[{style}]{s.composite:5.1f}[/{style}]",
                f"{s.correctness:5.1f}",
                f"{s.regression_safety:5.1f}",
                f"{s.security:5.1f}",
                f"{s.review_burden:5.1f}",
                f"{s.maintainability:5.1f}",
                f"{s.cost:5.1f}",
                f"{s.speed:5.1f}",
                str(s.n_results),
            )
    leader = ranked[0]
    subtitle = (
        f"[{MUTED}]Weights: correctness 35, regression-safety 20, "
        f"security 15, review 10, maintainability 8, cost 7, speed 5.[/{MUTED}]"
    )
    console.print(
        Panel(
            table,
            title="Production Readiness Score",
            subtitle=subtitle,
            border_style=INFO,
            expand=False,
        )
    )
    console.print(
        f"\n[{MUTED}]Inspect the leader's traces:[/{MUTED}] "
        f"awb trace grade <run_dir>  [{MUTED}]# top tool: {leader.tool}[/{MUTED}]"
    )
