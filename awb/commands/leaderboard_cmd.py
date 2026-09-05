"""leaderboard command — generate HTML leaderboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from awb.commands._shared import INFO, MUTED, console, emit_json, score_style

# Heuristic thresholds for mapping RunResult fields onto the 7 readiness
# dimensions. Single source of truth lives in awb.scoring.readiness; re-exported
# here because this is where they're documented + tuned.
from awb.scoring.readiness import (  # noqa: E402
    COST_USD_TO_ZERO,
    MAINTAINABILITY_LINT_TO_ZERO,
    REVIEW_BURDEN_FILES_TO_ZERO,
    SPEED_SECONDS_TO_ZERO,
)

__all__ = [
    "COST_USD_TO_ZERO",
    "MAINTAINABILITY_LINT_TO_ZERO",
    "REVIEW_BURDEN_FILES_TO_ZERO",
    "SPEED_SECONDS_TO_ZERO",
    "leaderboard",
]


@dataclass
class ToolReadiness:
    tool: str
    n_results: int
    composite: float | None
    correctness: float
    regression_safety: float | None
    security: float | None
    review_burden: float
    maintainability: float
    cost: float
    speed: float
    cohort_id: str = ""
    comparison_eligible: bool = False
    ineligibility_reasons: list[str] | None = None


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
    from awb.scoring.readiness import readiness_from_results

    recorder = ResultRecorder()
    runs = recorder.load_all_runs()
    from awb.scoring.cohorts import cohort_group_key, identity_from_result

    by_cohort: dict[str, list] = {}
    for results in runs.values():
        for r in results:
            by_cohort.setdefault(cohort_group_key(r), []).append(r)
    out: list[ToolReadiness] = []
    for cohort_id, cohort_results in sorted(by_cohort.items()):
        identity = identity_from_result(cohort_results[0])
        d = readiness_from_results(cohort_results)
        out.append(
            ToolReadiness(
                tool=cohort_results[0].tool,
                n_results=d["n_results"],
                composite=d["composite"],
                correctness=d["correctness"],
                regression_safety=d["regression_safety"],
                security=d["security"],
                review_burden=d["review_burden"],
                maintainability=d["maintainability"],
                cost=d["cost"],
                speed=d["speed"],
                cohort_id=cohort_id,
                comparison_eligible=identity.eligible,
                ineligibility_reasons=[f"missing {name}" for name in identity.missing_fields],
            )
        )
    out.sort(key=lambda s: (not s.comparison_eligible, -(s.composite or -1), s.tool))
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
            style = score_style(s.composite) if s.composite is not None else MUTED
            score = f"{s.composite:5.1f}" if s.composite is not None else "  n/a"
            table.add_row(
                str(i),
                s.tool,
                f"[{style}]{score}[/{style}]",
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
            style = score_style(s.composite) if s.composite is not None else MUTED
            score = f"{s.composite:5.1f}" if s.composite is not None else "  n/a"
            table.add_row(
                str(i),
                s.tool,
                f"[{style}]{score}[/{style}]",
                f"{s.correctness:5.1f}",
                f"{s.regression_safety:5.1f}" if s.regression_safety is not None else "  n/a",
                f"{s.security:5.1f}" if s.security is not None else "  n/a",
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
