"""Score report dataclass and formatted output."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from awb.scoring.capabilities import CapabilityProfile
from awb.scoring.composite import compute_composite_score
from awb.scoring.normalize import (
    normalize_cost,
    normalize_iterations,
    normalize_partial_credit,
    normalize_quality,
    normalize_regressions,
    normalize_security,
    normalize_speed,
    normalize_success_rate,
)


@dataclass
class ScoreReport:
    tool: str
    composite_score: float
    per_metric_scores: dict[str, float] = field(default_factory=dict)
    per_metric_normalized: dict[str, float] = field(default_factory=dict)
    capability_profile: CapabilityProfile | None = None


def generate_report(tool_stats: dict) -> ScoreReport:
    n = tool_stats["total_tasks"] or 1
    success = normalize_success_rate(tool_stats["success_rate"])
    partial = normalize_partial_credit(tool_stats["avg_score_pct"])
    correctness = 0.6 * success + 0.4 * partial

    raw = {
        "correctness": tool_stats["success_rate"],
        "cost_efficiency": tool_stats["avg_cost"],
        "speed": tool_stats["avg_time"],
        "code_quality": tool_stats["total_lint_delta"],
        "reliability": tool_stats["total_regressions"],
        "security": tool_stats["total_security_delta"],
        "efficiency": tool_stats["avg_iterations"],
    }
    normalized = {
        "correctness": round(correctness, 1),
        "cost_efficiency": normalize_cost(tool_stats["avg_cost"]),
        "speed": normalize_speed(tool_stats["avg_time"]),
        "code_quality": normalize_quality(tool_stats["total_lint_delta"], n),
        "reliability": normalize_regressions(tool_stats["total_regressions"], n),
        "security": normalize_security(tool_stats["total_security_delta"], n),
        "efficiency": normalize_iterations(tool_stats["avg_iterations"]),
    }
    composite = compute_composite_score(tool_stats)
    return ScoreReport(
        tool=tool_stats["tool"],
        composite_score=composite,
        per_metric_scores=raw,
        per_metric_normalized=normalized,
    )


def print_report(report: ScoreReport) -> None:
    from awb.scoring.composite import load_weight_profile

    console = Console()
    score = report.composite_score
    console.print(f"\n[bold]{report.tool}[/bold] - Composite: [bold cyan]{score}[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Raw", justify="right")
    table.add_column("Normalized", justify="right")
    table.add_column("Weight", justify="right")

    weights = load_weight_profile()
    for metric, weight in weights.items():
        raw = report.per_metric_scores.get(metric, 0)
        norm = report.per_metric_normalized.get(metric, 0)
        table.add_row(
            metric,
            f"{raw:.2f}" if isinstance(raw, float) else str(raw),
            f"{norm:.1f}",
            f"{weight:.0%}",
        )

    console.print(table)

    if report.capability_profile:
        console.print("\n[bold]Capability Profile:[/bold]")
        for cap_name, cap_score in report.capability_profile.scores.items():
            if cap_score.score is None:
                bar = " " * 20
                score_str = "  n/a"
                tasks_str = ""
            else:
                filled = round(cap_score.score / 100 * 20)
                bar = "=" * filled + " " * (20 - filled)
                score_str = f"{cap_score.score:5.1f}"
                tasks_str = f"  ({cap_score.tasks_tested} tasks)"
            label = f"  {cap_name:<24}"
            console.print(f"{label}|{bar}| {score_str}{tasks_str}")
