"""The exported submission (baseline) must carry trace grades + readiness.

The published baseline only had outcome/metrics/cost/quality, so the two
flagship trust features (trace grading, Production Readiness Score) were
invisible in the one public artifact. build_submission now embeds per-run
trace grades (null when the trace is span-less) and a submission-level
readiness block, so a regenerated baseline showcases them.
"""

from __future__ import annotations

import pytest

from awb.commands.submit import build_submission
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
)
from awb.trace import FILE_EDIT, TraceWriter, new_span


def _result(task_id, *, success, trace_path=""):
    return RunResult(
        task_id=task_id,
        tool="claude-code-custom",
        run_id="r1",
        timestamp="2026-05-30T00:00:00Z",
        outcome=RunOutcome(
            success=success,
            partial_credit_score=100 if success else 0,
            partial_credit_max=100,
        ),
        metrics=RunMetrics(wall_clock_seconds=42.0, files_modified=1),
        cost=RunCost(estimated_cost_usd=0.5),
        quality=RunQuality(test_regressions=0, security_delta=0, lint_delta=0),
        environment=RunEnvironment(os="darwin", hardware="test"),
        trace_path=trace_path,
    )


def test_submission_includes_readiness_block(tmp_path):
    results = [_result("BF-001", success=True), _result("BF-002", success=False)]
    for result in results:
        result.quality.test_regressions_status = "measured_clean"
        result.quality.security_status = "measured_clean"
    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")
    assert "readiness" in sub["submission"]
    r = sub["submission"]["readiness"]
    assert 0 <= r["composite"] <= 100
    # One of two passed -> correctness 50.
    assert r["correctness"] == 50.0


def test_submission_preserves_one_consistent_task_set_hash(tmp_path):
    results = [_result("BF-001", success=True), _result("BF-002", success=True)]
    for result in results:
        result.task_set_hash = "ab" * 32

    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")

    assert sub["submission"]["task_set_hash"] == "ab" * 32


def test_submission_marks_mixed_task_sets_ineligible(tmp_path):
    results = [_result("BF-001", success=True), _result("BF-002", success=True)]
    results[0].task_set_hash = "ab" * 32
    results[1].task_set_hash = "cd" * 32

    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")

    assert "task_set_hash" not in sub["submission"]
    assert sub["submission"]["comparison_eligibility"]["eligible"] is False
    assert "mixed task_set_hash" in sub["submission"]["comparison_eligibility"]["reasons"]


def test_export_with_missing_measurements_still_validates(tmp_path):
    from awb.submission.ingest import validate_submission

    sub = build_submission(
        [_result("BF-001", success=False)], run_dir=tmp_path, task_defs={}, submitter="me"
    )

    assert sub["submission"]["readiness"]["composite"] is None
    assert validate_submission(sub) == []


def test_complete_matching_submission_identity_is_comparison_eligible(tmp_path):
    from awb.submission.compare import compare_submissions
    from awb.submission.ingest import parse_submission

    result = _result("BF-001", success=True)
    result.task_set_hash = "ab" * 32
    result.model = "model-a"
    result.tool_version = "1.2.3"
    result.effective_config_hash = "config-a"
    result.evaluator_version = "evaluator-a"
    result.execution_mode = "local"
    result.environment_fingerprint = "env-a"
    result.budget_fingerprint = "budget-a"
    data = build_submission([result], run_dir=tmp_path, task_defs={}, submitter="me")
    submission = parse_submission(data)

    comparison = compare_submissions(submission, submission)

    assert submission.comparison_eligible is True
    assert comparison.comparison_eligible is True
    assert comparison.eligibility_warning == ""


def test_quality_measurement_status_survives_submission_ingest(tmp_path):
    from awb.submission.ingest import parse_submission, submission_to_run_results

    result = _result("BF-001", success=True)
    result.quality.security_status = "measured_clean"
    result.quality.test_regressions_status = "measured_clean"
    data = build_submission([result], run_dir=tmp_path, task_defs={}, submitter="me")

    [loaded] = submission_to_run_results(parse_submission(data))

    assert loaded.quality.security_status == "measured_clean"
    assert loaded.quality.test_regressions_status == "measured_clean"


def test_run_carries_trace_grade_when_spans_present(tmp_path):
    # Write a trace with a real FILE_EDIT span for BF-001.
    trace_rel = "BF-001_claude-code-custom.trace.jsonl"
    with TraceWriter(tmp_path / trace_rel) as w:
        w.write(new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "edit"}))

    results = [_result("BF-001", success=True, trace_path=trace_rel)]
    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")
    run0 = sub["results"][0]["runs"][0]
    assert run0["trace_grade"] is not None
    assert "read_tests_before_edit" in run0["trace_grade"]


def test_run_trace_grade_is_null_when_no_spans(tmp_path):
    # No trace file on disk -> trace_grade null, not a fake 100.
    results = [_result("BF-001", success=True, trace_path="missing.trace.jsonl")]
    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")
    assert sub["results"][0]["runs"][0]["trace_grade"] is None


def test_trace_summary_averages_all_six_rubrics_when_gradeable():
    from awb.commands.submit import _mean_trace_summary

    grades = [
        {
            "read_tests_before_edit": 100,
            "ran_verification_after_change": 100,
            "no_out_of_scope_edits": 100,
            "no_repeated_failing_command_loop": 100,
            "context_discipline": 80,
            "tool_call_efficiency": 60,
        },
        {
            "read_tests_before_edit": 0,
            "ran_verification_after_change": 0,
            "no_out_of_scope_edits": 0,
            "no_repeated_failing_command_loop": 0,
            "context_discipline": 100,
            "tool_call_efficiency": 100,
        },
    ]
    summary = _mean_trace_summary(grades)
    assert set(summary.keys()) == {
        "read_tests_before_edit",
        "ran_verification_after_change",
        "no_out_of_scope_edits",
        "no_repeated_failing_command_loop",
        "context_discipline",
        "tool_call_efficiency",
    }
    assert summary["context_discipline"] == pytest.approx(90.0)
    assert summary["tool_call_efficiency"] == pytest.approx(80.0)


def test_trace_summary_averages_new_rubric_only_over_runs_that_reported_it():
    """context_discipline/tool_call_efficiency are omitted per-run when not
    gradeable - the mean must not treat a missing key as zero."""
    from awb.commands.submit import _mean_trace_summary

    grades = [
        {
            "read_tests_before_edit": 100,
            "ran_verification_after_change": 100,
            "no_out_of_scope_edits": 100,
            "no_repeated_failing_command_loop": 100,
            "context_discipline": 40,
        },
        {
            "read_tests_before_edit": 0,
            "ran_verification_after_change": 0,
            "no_out_of_scope_edits": 0,
            "no_repeated_failing_command_loop": 0,
            # no context_discipline for this run - not gradeable
        },
    ]
    summary = _mean_trace_summary(grades)
    assert summary["context_discipline"] == pytest.approx(40.0)
    assert "tool_call_efficiency" not in summary
