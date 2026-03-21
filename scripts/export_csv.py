#!/usr/bin/env python3
"""Export benchmark results to CSV."""
import csv
import sys

from awb.core.results import ResultRecorder


def main():
    recorder = ResultRecorder()
    all_runs = recorder.load_all_runs()

    if not all_runs:
        print("No results found")
        return

    writer = csv.writer(sys.stdout)
    writer.writerow([
        "run_id", "task_id", "tool", "model", "success",
        "partial_score", "partial_max", "wall_clock_s",
        "iterations", "cost_usd", "lint_delta", "security_delta", "regressions"
    ])

    for _, results in sorted(all_runs.items()):
        for r in results:
            writer.writerow([
                r.run_id, r.task_id, r.tool, r.model, r.outcome.success,
                r.outcome.partial_credit_score, r.outcome.partial_credit_max,
                r.metrics.wall_clock_seconds, r.metrics.iteration_count,
                r.cost.estimated_cost_usd, r.quality.lint_delta,
                r.quality.security_delta, r.quality.test_regressions,
            ])


if __name__ == "__main__":
    main()
