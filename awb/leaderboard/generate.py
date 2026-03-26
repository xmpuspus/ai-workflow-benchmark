"""Generate static HTML leaderboard from benchmark results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from awb.core.config import RESULTS_DIR
from awb.scoring.composite import compute_composite_score


def load_results(results_dir: Path | None = None) -> list[dict]:
    """Load all result JSON files from results/runs/."""
    results_dir = results_dir or RESULTS_DIR
    results = []
    if not results_dir.exists():
        return results
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        for json_file in sorted(run_dir.glob("*.json")):
            with open(json_file) as f:
                results.append(json.load(f))
    return results


def aggregate_by_tool(results: list[dict]) -> dict[str, dict]:
    """Aggregate results by tool name. Returns per-tool summary stats."""
    tools = {}
    for r in results:
        tool = r["tool"]
        if tool not in tools:
            tools[tool] = {
                "tool": tool,
                "model": r.get("model", "unknown"),
                "runs": [],
                "total_tasks": 0,
                "successes": 0,
                "total_score": 0,
                "total_max_score": 0,
                "total_time": 0.0,
                "total_cost": 0.0,
                "total_iterations": 0,
                "total_lint_delta": 0,
                "total_security_delta": 0,
                "total_regressions": 0,
            }
        t = tools[tool]
        t["runs"].append(r)
        t["total_tasks"] += 1
        if r["outcome"]["success"]:
            t["successes"] += 1
        t["total_score"] += r["outcome"]["partial_credit_score"]
        t["total_max_score"] += r["outcome"]["partial_credit_max"]
        t["total_time"] += r["metrics"]["wall_clock_seconds"]
        t["total_cost"] += r["cost"]["estimated_cost_usd"]
        t["total_iterations"] += r["metrics"]["iteration_count"]
        t["total_lint_delta"] += r["quality"]["lint_delta"]
        t["total_security_delta"] += r["quality"]["security_delta"]
        t["total_regressions"] += r["quality"]["test_regressions"]

    for t in tools.values():
        n = t["total_tasks"] or 1
        t["success_rate"] = round(t["successes"] / n * 100, 1)
        t["avg_score_pct"] = round(t["total_score"] / max(t["total_max_score"], 1) * 100, 1)
        t["avg_time"] = round(t["total_time"] / n, 1)
        t["avg_cost"] = round(t["total_cost"] / n, 2)
        t["avg_iterations"] = round(t["total_iterations"] / n, 1)

    return tools


def generate_leaderboard(
    results_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Generate static HTML leaderboard. Returns path to output index.html."""
    leaderboard_dir = Path(__file__).resolve().parent
    output_dir = output_dir or leaderboard_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = load_results(results_dir)
    tools = aggregate_by_tool(results)

    for tool_stats in tools.values():
        tool_stats["composite_score"] = compute_composite_score(tool_stats)

    ranked = sorted(tools.values(), key=lambda t: t["composite_score"], reverse=True)

    task_results = {}
    for r in results:
        tid = r["task_id"]
        if tid not in task_results:
            task_results[tid] = {}
        task_results[tid][r["tool"]] = r

    env = Environment(
        loader=FileSystemLoader(str(leaderboard_dir / "templates")),
        autoescape=True,
    )
    template = env.get_template("index.html")
    html = template.render(
        tools=ranked,
        task_results=task_results,
        total_results=len(results),
        results_json=json.dumps(results, indent=2),
    )

    output_path = output_dir / "index.html"
    output_path.write_text(html)

    # Append this run's scores to history for trend tracking
    history_path = output_dir / "data" / "history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except json.JSONDecodeError:
            history = []
    history.append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": {t["tool"]: t.get("composite_score", 0) for t in ranked},
        }
    )
    history_path.write_text(json.dumps(history, indent=2))

    static_src = leaderboard_dir / "static"
    static_dst = output_dir / "static"
    static_dst.mkdir(exist_ok=True)
    for f in static_src.iterdir():
        if f.is_file():
            (static_dst / f.name).write_text(f.read_text())

    return output_path
