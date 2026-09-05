import json

from awb.leaderboard.generate import aggregate_by_tool, generate_leaderboard


def _result(run_id: str, *, model: str = "model-a", complete: bool = True) -> dict:
    result = {
        "task_id": "BF-001",
        "tool": "tool",
        "run_id": run_id,
        "timestamp": "2026-09-05T00:00:00Z",
        "model": model,
        "tool_version": "1.2.3" if complete else "",
        "task_set_hash": "ab" * 32 if complete else "",
        "effective_config_hash": "config-a" if complete else "",
        "evaluator_version": "evaluator-a" if complete else "",
        "execution_mode": "local" if complete else "",
        "environment_fingerprint": "env-a" if complete else "",
        "budget_fingerprint": "budget-a" if complete else "",
        "outcome": {
            "success": True,
            "partial_credit_score": 100,
            "partial_credit_max": 100,
            "breakdown": [],
        },
        "metrics": {
            "wall_clock_seconds": 1,
            "iteration_count": 1,
            "human_interventions": 0,
            "tool_calls": {},
            "files_modified": 1,
            "lines_changed": 1,
        },
        "cost": {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0},
        "quality": {
            "lint_delta": 0,
            "security_delta": 0,
            "test_regressions": 0,
            "security_status": "measured_clean" if complete else "missing",
            "test_regressions_status": "measured_clean" if complete else "missing",
        },
        "environment": {
            "os": "test",
            "hardware": "test",
            "python_version": "3.13",
            "awb_version": "1.7.0",
            "adapter_version": "1.2.3" if complete else "",
            "pip_freeze_hash": "deps" if complete else "",
        },
    }
    return result


def test_aggregate_partitions_same_tool_by_model_identity():
    cohorts = aggregate_by_tool(
        [_result("exp_run1", model="model-a"), _result("exp_run1", model="model-b")]
    )

    assert len(cohorts) == 2
    assert all(cohort["comparison_eligible"] for cohort in cohorts.values())


def test_legacy_experiments_remain_separate_and_ineligible():
    cohorts = aggregate_by_tool(
        [_result("first_run1", complete=False), _result("second_run1", complete=False)]
    )

    assert len(cohorts) == 2
    assert all(not cohort["comparison_eligible"] for cohort in cohorts.values())
    assert all(
        "missing task_set_hash" in cohort["ineligibility_reasons"] for cohort in cohorts.values()
    )


def test_generated_legacy_row_is_visible_but_unranked_and_has_no_chart(tmp_path):
    results_dir = tmp_path / "runs"
    run_dir = results_dir / "legacy"
    run_dir.mkdir(parents=True)
    (run_dir / "BF-001_tool.json").write_text(json.dumps(_result("legacy_run1", complete=False)))

    output = generate_leaderboard(results_dir=results_dir, output_dir=tmp_path / "out")
    html = output.read_text()

    assert "Not comparison eligible" in html
    assert '<td class="rank">n/a</td>' in html
    assert '<div class="chart-section">' not in html
