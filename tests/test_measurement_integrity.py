from __future__ import annotations

from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)
from awb.scoring.cohorts import (
    assess_cohort_coverage,
    cohort_group_key,
    identity_from_mapping,
    identity_from_result,
)
from awb.scoring.readiness import readiness_from_results
from awb.scoring.workflow_lift import compute_workflow_lift
from awb.trace import FILE_EDIT, TraceWriter, new_span
from awb.trace.grader import grade_trace


def _result(task_id: str, score: float) -> RunResult:
    return RunResult(
        task_id=task_id,
        tool="tool",
        run_id="run",
        timestamp="2026-09-05T00:00:00Z",
        outcome=RunOutcome(
            success=score == 100,
            partial_credit_score=score,
            partial_credit_max=100,
        ),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )


def test_workflow_lift_uses_every_repeat_and_is_order_invariant():
    vanilla = [_result("T1", n) for n in (0, 50, 100)] + [_result("T2", n) for n in (20, 40)]
    custom = [_result("T1", n) for n in (100, 50, 0)] + [_result("T2", n) for n in (60, 80)]

    report = compute_workflow_lift(vanilla, custom, {})
    reversed_report = compute_workflow_lift(list(reversed(vanilla)), custom, {})

    assert report.lift == reversed_report.lift == 20.0
    assert report.aggregation == "mean_per_task"
    assert report.total_attempts_vanilla == 5
    assert report.total_attempts_custom == 5


def test_workflow_lift_unequal_repeats_are_inconclusive():
    vanilla = [_result("T1", 100)]
    custom = [_result("T1", 0), _result("T1", 0)]

    report = compute_workflow_lift(vanilla, custom, {})

    assert report.comparison_eligible is False
    assert report.n_tasks == 0
    assert report.p_value is None
    assert report.unpaired_attempts_custom == 1


def test_missing_quality_measurements_are_unknown_and_suppress_composite():
    score = readiness_from_results([_result("T1", 0)])

    assert score["regression_safety"] is None
    assert score["security"] is None
    assert score["composite"] is None
    assert score["coverage"]["regression_safety"]["measured"] == 0
    assert score["coverage"]["regression_safety"]["total"] == 1
    assert score["coverage"]["security"]["measured"] == 0
    assert score["coverage"]["security"]["total"] == 1


def test_explicit_measured_quality_status_can_earn_scores():
    result = _result("T1", 100)
    result.quality.test_regressions_status = "measured_clean"
    result.quality.security_status = "measured_clean"
    result.quality.lint_status = "measured_clean"
    result.cost.usage_status = "complete"

    score = readiness_from_results([result])

    assert score["regression_safety"] == 100.0
    assert score["security"] == 100.0
    assert score["composite"] == 100.0


def test_partial_quality_coverage_suppresses_readiness_composite():
    measured = _result("T1", 100)
    measured.quality.test_regressions_status = "measured_clean"
    measured.quality.security_status = "measured_clean"
    missing = _result("T2", 100)

    score = readiness_from_results([measured, missing])

    assert score["regression_safety"] is None
    assert score["security"] is None
    assert score["composite"] is None
    assert score["coverage"]["regression_safety"]["measured"] == 1
    assert score["coverage"]["regression_safety"]["total"] == 2


def test_scope_score_is_absent_without_explicit_allowed_edit_contract(tmp_path):
    trace = tmp_path / "scope.trace.jsonl"
    with TraceWriter(trace) as writer:
        writer.write(new_span(FILE_EDIT, attributes={"file.path": "src/x.py"}))

    assert "no_out_of_scope_edits" not in grade_trace(trace)
    assert grade_trace(trace, allowed_edit_paths=["src/x.py"])["no_out_of_scope_edits"] == 100


def test_complete_cohort_identity_is_eligible_and_model_changes_partition():
    first = _result("T1", 100)
    second = _result("T1", 100)
    for result in (first, second):
        result.task_set_hash = "ab" * 32
        result.model = "model-a"
        result.tool_version = "1.2.3"
        result.effective_config_hash = "config-a"
        result.evaluator_version = "evaluator-a"
        result.execution_mode = "local"
        result.environment_fingerprint = "env-a"
        result.budget_fingerprint = "budget-a"
        result.cohort_manifest = {"selected_task_ids": ["T1"], "requested_repeats": 1}

    assert identity_from_result(first).eligible is True
    assert cohort_group_key(first) == cohort_group_key(second)
    second.model = "model-b"
    assert cohort_group_key(first) != cohort_group_key(second)


def test_cohort_identity_partitions_different_tools():
    first = _result("T1", 100)
    second = _result("T1", 100)
    for result in (first, second):
        result.task_set_hash = "suite"
        result.model = "model"
        result.adapter_version = "adapter"
        result.effective_config_hash = "config"
        result.evaluator_version = "evaluator"
        result.execution_mode = "host"
        result.environment_fingerprint = "environment"
        result.budget_fingerprint = "budget"
        result.cohort_manifest = {"selected_task_ids": ["T1"], "requested_repeats": 1}
    second.tool = "other-tool"

    assert cohort_group_key(first) != cohort_group_key(second)


def test_malformed_task_selection_is_missing_instead_of_raising():
    identity = identity_from_mapping(
        {
            "tool": "tool",
            "cohort_manifest": {
                "selected_task_ids": ["T1", None],
                "requested_repeats": 1,
            },
        }
    )

    assert identity.selection_identity == ""
    assert "selection_identity" in identity.missing_fields


def test_cohort_uses_suite_and_selection_identity_not_per_task_definition_hash():
    first = _result("T1", 100)
    second = _result("T2", 100)
    for result in (first, second):
        result.task_set_hash = "suite"
        result.model = "model"
        result.adapter_version = "adapter"
        result.effective_config_hash = "config"
        result.evaluator_version = "evaluator"
        result.execution_mode = "host"
        result.environment_fingerprint = "environment"
        result.budget_fingerprint = "budget"
        result.cohort_manifest = {"selected_task_ids": ["T1", "T2"], "requested_repeats": 1}
    first.task_definition_hash = "task-one"
    second.task_definition_hash = "task-two"

    assert cohort_group_key(first) == cohort_group_key(second)
    assert assess_cohort_coverage([first, second]).eligible is True


def test_cohort_rejects_unknown_identity_and_incomplete_repeat_grid():
    result = _result("T1", 100)
    result.task_set_hash = "suite"
    result.model = "unknown"
    result.adapter_version = "adapter"
    result.effective_config_hash = "config"
    result.evaluator_version = "evaluator"
    result.execution_mode = "host"
    result.environment_fingerprint = "environment"
    result.budget_fingerprint = "budget"
    result.task_definition_hash = "task-one"
    result.cohort_manifest = {"selected_task_ids": ["T1", "T2"], "requested_repeats": 2}

    assert "model" in identity_from_result(result).missing_fields
    coverage = assess_cohort_coverage([result])
    assert coverage.eligible is False
    assert any("task-repeat grid" in reason for reason in coverage.reasons)


def test_cohort_adapter_version_falls_back_from_unknown_flat_field():
    result = _result("T1", 100)
    result.adapter_version = "unknown"
    result.tool_version = "tool-version"

    assert identity_from_result(result).adapter_version == "tool-version"


def test_cohort_rejects_duplicate_repeat_identity_and_task_definition_drift():
    first = _result("T1", 100)
    second = _result("T1", 100)
    for result in (first, second):
        result.run_id = "experiment_run1"
        result.task_set_hash = "suite"
        result.model = "model"
        result.adapter_version = "adapter"
        result.effective_config_hash = "config"
        result.evaluator_version = "evaluator"
        result.execution_mode = "host"
        result.environment_fingerprint = "environment"
        result.budget_fingerprint = "budget"
        result.cohort_manifest = {"selected_task_ids": ["T1"], "requested_repeats": 2}
    first.task_definition_hash = "task-one"
    second.task_definition_hash = "task-two"

    coverage = assess_cohort_coverage([first, second])

    assert coverage.eligible is False
    assert "invalid repeat identities for T1" in coverage.reasons
    assert "task definition changed within cohort" in coverage.reasons


def test_legacy_result_is_ineligible_and_partitioned_by_experiment():
    first = _result("T1", 100)
    second = _result("T2", 100)
    first.run_id = "experiment-a_run1"
    second.run_id = "experiment-b_run1"

    assert identity_from_result(first).eligible is False
    assert cohort_group_key(first) != cohort_group_key(second)


def test_trace_command_reads_serialized_allowed_edit_contract(tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from awb.commands import trace_cmd

    trace_path = tmp_path / "BF-001_tool.trace.jsonl"
    trace_path.write_text("")
    (tmp_path / "BF-001_tool.json").write_text(
        json.dumps({"allowed_edit_paths": ["src/allowed.py"]})
    )
    seen = {}

    def _fake_grade(path, files_to_examine=None, *, allowed_edit_paths=None):
        seen["allowed_edit_paths"] = allowed_edit_paths
        return {
            "read_tests_before_edit": 100,
            "ran_verification_after_change": 100,
            "no_out_of_scope_edits": 100,
            "no_repeated_failing_command_loop": 100,
        }

    monkeypatch.setattr(trace_cmd, "grade_trace_or_none", _fake_grade)

    result = CliRunner().invoke(trace_cmd.trace, ["grade", str(tmp_path)])

    assert result.exit_code == 0
    assert seen["allowed_edit_paths"] == ["src/allowed.py"]


def test_trace_command_empty_trace_is_null_in_json(tmp_path):
    import json

    from click.testing import CliRunner

    from awb.commands import trace_cmd

    (tmp_path / "BF-001_tool.trace.jsonl").write_text("")
    result = CliRunner().invoke(trace_cmd.trace, ["grade", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["scores"] is None


def test_readiness_panel_uses_na_rank_for_ineligible_cohort(monkeypatch):
    from rich.console import Console

    from awb.commands import leaderboard_cmd

    output = Console(record=True, width=180)
    monkeypatch.setattr(leaderboard_cmd, "console", output)
    score = leaderboard_cmd.ToolReadiness(
        tool="legacy",
        n_results=1,
        composite=None,
        correctness=100,
        regression_safety=None,
        security=None,
        review_burden=100,
        maintainability=None,
        cost=None,
        speed=100,
        comparison_eligible=False,
        ineligibility_reasons=["missing evidence"],
    )

    leaderboard_cmd._render_readiness_panel([score], explain=False)
    rendered = output.export_text()

    assert "n/a" in rendered
    assert "ineligible: missing evidence" in rendered
    assert "top tool" not in rendered
