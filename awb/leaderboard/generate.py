"""Generate static HTML leaderboard from benchmark results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from awb.core.config import RESULTS_DIR
from awb.core.results import _dict_to_result
from awb.core.task_loader import load_all_tasks
from awb.scoring.cohorts import cohort_group_key_mapping, identity_from_mapping
from awb.scoring.composite import compute_aggregate_score


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
    """Aggregate only within compatible experiment identities."""
    tools = {}
    for r in results:
        tool = r["tool"]
        cohort_key = cohort_group_key_mapping(r)
        if cohort_key not in tools:
            identity = identity_from_mapping(r)
            tools[cohort_key] = {
                "tool": tool,
                "model": r.get("model", "unknown"),
                "cohort_id": cohort_key,
                "identity_hash": identity.cohort_id,
                "comparison_eligible": identity.eligible,
                "ineligibility_reasons": [f"missing {name}" for name in identity.missing_fields],
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
                "security_measurements": 0,
                "regression_measurements": 0,
            }
        t = tools[cohort_key]
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
        if r["quality"].get("security_status") in {
            "measured",
            "measured_clean",
            "measured_findings",
        }:
            t["security_measurements"] += 1
        if r["quality"].get("test_regressions_status") in {
            "measured",
            "measured_clean",
            "measured_findings",
        }:
            t["regression_measurements"] += 1

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
    """Generate static HTML leaderboard. Returns path to output index.html.

    Default output_dir is `./results/leaderboard/` in the current working
    directory. Writing under the package install dir breaks on read-only
    installs and pollutes site-packages.
    """
    leaderboard_dir = Path(__file__).resolve().parent
    output_dir = output_dir or Path.cwd() / "results" / "leaderboard"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = load_results(results_dir)
    tools = aggregate_by_tool(results)

    # Load task definitions for per-task scoring
    all_tasks = load_all_tasks()
    task_defs = {t.id: t for t in all_tasks}

    for tool_stats in tools.values():
        run_results = [_dict_to_result(r) for r in tool_stats["runs"]]
        agg_score, _ = compute_aggregate_score(run_results, task_defs)
        tool_stats["composite_score"] = agg_score
        if agg_score is None:
            tool_stats["comparison_eligible"] = False
            tool_stats["ineligibility_reasons"].append("missing quality measurement coverage")

    ranked = sorted(
        tools.values(),
        key=lambda t: (
            not t["comparison_eligible"],
            -(t["composite_score"] if t["composite_score"] is not None else -1),
            t["tool"],
        ),
    )
    rank = 0
    for tool_stats in ranked:
        if tool_stats["comparison_eligible"]:
            rank += 1
            tool_stats["rank"] = rank
        else:
            tool_stats["rank"] = None

    task_results = {}
    for r in results:
        tid = r["task_id"]
        if tid not in task_results:
            task_results[tid] = {}
        cohort_key = cohort_group_key_mapping(r)
        task_results[tid][f"{r['tool']} · {cohort_key}"] = r

    env = Environment(
        loader=FileSystemLoader(str(leaderboard_dir / "templates")),
        autoescape=True,
    )
    template = env.get_template("index.html")
    eligibility_by_cohort = {
        tool_stats["cohort_id"]: tool_stats["comparison_eligible"] for tool_stats in ranked
    }
    render_results = []
    for result in results:
        rendered = dict(result)
        cohort_key = cohort_group_key_mapping(result)
        rendered["cohort_id"] = cohort_key
        rendered["comparison_eligible"] = eligibility_by_cohort[cohort_key]
        render_results.append(rendered)

    html = template.render(
        tools=ranked,
        task_results=task_results,
        total_results=len(results),
        comparison_eligible_count=sum(t["comparison_eligible"] for t in ranked),
        results_json=json.dumps(render_results, indent=2),
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
            "tools": {t["cohort_id"]: t.get("composite_score", 0) for t in ranked},
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
