"""Cost-per-solved-task report grouped by tool and billing unit."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class CostReport:
    tool: str
    n_tasks: int
    n_solved: int
    total_cost_usd: float
    cost_per_task: float
    cost_per_solved: float | None
    wasted_cost_usd: float
    total_tokens: int
    tokens_per_solved: float | None
    total_credits: float | None
    credits_per_task: float | None
    credits_per_solved: float | None
    wasted_credits: float | None


def build_cost_report(results) -> list[CostReport]:
    """Group RunResults by tool and compute cost-per-solved-task figures.

    cost_per_solved and tokens_per_solved are None when a tool solved zero
    tasks - never divide by zero. Sorted cheapest-per-solved first, with
    None (nothing solved) sorting last.
    """
    by_tool: dict[str, list] = defaultdict(list)
    for r in results:
        by_tool[r.tool].append(r)

    reports = []
    for tool, rs in by_tool.items():
        n_tasks = len(rs)
        solved = [r for r in rs if r.outcome.success]
        n_solved = len(solved)
        # `or 0`: deserialized results can carry present-but-null cost fields
        # (dict.get returns the None, not the default).
        total_cost = sum(r.cost.estimated_cost_usd or 0.0 for r in rs)
        wasted_cost = sum(r.cost.estimated_cost_usd or 0.0 for r in rs if not r.outcome.success)
        total_tokens = sum((r.cost.input_tokens or 0) + (r.cost.output_tokens or 0) for r in rs)
        credit_values = [
            r.cost.estimated_credits for r in rs if r.cost.estimated_credits is not None
        ]
        total_credits = sum(credit_values) if credit_values else None
        wasted_credit_values = [
            r.cost.estimated_credits
            for r in rs
            if not r.outcome.success and r.cost.estimated_credits is not None
        ]
        wasted_credits = sum(wasted_credit_values) if credit_values else None
        cost_per_task = total_cost / n_tasks if n_tasks else 0.0
        cost_per_solved = (total_cost / n_solved) if n_solved else None
        tokens_per_solved = (total_tokens / n_solved) if n_solved else None
        reports.append(
            CostReport(
                tool=tool,
                n_tasks=n_tasks,
                n_solved=n_solved,
                total_cost_usd=round(total_cost, 4),
                cost_per_task=round(cost_per_task, 4),
                cost_per_solved=round(cost_per_solved, 4) if cost_per_solved is not None else None,
                wasted_cost_usd=round(wasted_cost, 4),
                total_tokens=total_tokens,
                tokens_per_solved=(
                    round(tokens_per_solved, 1) if tokens_per_solved is not None else None
                ),
                total_credits=round(total_credits, 4) if total_credits is not None else None,
                credits_per_task=(
                    round(total_credits / n_tasks, 4)
                    if total_credits is not None and n_tasks
                    else None
                ),
                credits_per_solved=(
                    round(total_credits / n_solved, 4)
                    if total_credits is not None and n_solved
                    else None
                ),
                wasted_credits=(round(wasted_credits, 4) if wasted_credits is not None else None),
            )
        )

    reports.sort(
        key=lambda c: (c.cost_per_solved is None, c.cost_per_solved if c.cost_per_solved else 0.0)
    )
    return reports
