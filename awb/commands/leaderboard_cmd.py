"""leaderboard command — generate HTML leaderboard."""

from __future__ import annotations

from pathlib import Path

import click

from awb.commands._shared import console


@click.command()
@click.option("--output-dir", type=click.Path(), help="Output directory")
@click.option(
    "--readiness",
    is_flag=True,
    default=False,
    help="Print Production Readiness Score (0-100) per tool to stdout in addition to the HTML.",
)
def leaderboard(output_dir: str | None, readiness: bool):
    """Generate HTML leaderboard from results."""
    from awb.leaderboard.generate import generate_leaderboard

    out = Path(output_dir) if output_dir else None
    path = generate_leaderboard(output_dir=out)
    console.print(f"Leaderboard generated: [bold]{path}[/bold]")

    if readiness:
        _print_readiness_summary()


def _print_readiness_summary() -> None:
    """Compute and print Production Readiness Score for each tool seen in results."""
    from awb.core.config import RESULTS_DIR
    from awb.core.results import ResultRecorder
    from awb.scoring.readiness import compute_readiness_score

    recorder = ResultRecorder()
    runs = recorder.load_all_runs()
    by_tool: dict[str, list] = {}
    for results in runs.values():
        for r in results:
            by_tool.setdefault(r.tool, []).append(r)

    if not by_tool:
        console.print(
            f"[yellow]No results found in {RESULTS_DIR} — readiness summary skipped.[/yellow]"
        )
        return

    console.print("\n[bold]Production Readiness Score[/bold]\n")
    console.print(f"  {'tool':<32} {'readiness':>9}")
    console.print(f"  {'-' * 32} {'-' * 9}")
    for tool in sorted(by_tool.keys()):
        results = by_tool[tool]
        n = len(results) or 1

        def _mean(fn, _results=results, _n=n):
            return sum(fn(r) for r in _results) / _n

        # Map result fields onto the 7 readiness dimensions on a 0-100 scale.
        correctness = 100.0 * sum(1 for r in results if r.outcome.success) / n
        regression_safety = 100.0 * sum(
            1 for r in results if r.quality.test_regressions == 0
        ) / n
        security = 100.0 * sum(1 for r in results if r.quality.security_delta <= 0) / n
        # Review burden: fewer modified files + lines = lower burden = higher score.
        # Heuristic: 0 changes -> 100, 50+ files -> ~0; same for lines >= 1000.
        review_burden = 100.0 - min(100.0, _mean(lambda r: r.metrics.files_modified) * 2.0)
        maintainability = 100.0 - min(
            100.0, max(0.0, _mean(lambda r: r.quality.lint_delta) * 5.0)
        )
        # Cost: $0 -> 100, $5 -> 0
        cost = max(0.0, 100.0 - 20.0 * _mean(lambda r: r.cost.estimated_cost_usd))
        # Speed: 0s -> 100, 1800s -> 0
        speed = max(0.0, 100.0 - _mean(lambda r: r.metrics.wall_clock_seconds) / 18.0)

        score = compute_readiness_score(
            correctness=correctness,
            regression_safety=regression_safety,
            security=security,
            review_burden=review_burden,
            maintainability=maintainability,
            cost=cost,
            speed=speed,
        )
        console.print(f"  {tool[:32]:<32} {score:>9.1f}")
