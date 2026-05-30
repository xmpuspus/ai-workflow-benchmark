"""The exported submission (baseline) must carry trace grades + readiness.

The published baseline only had outcome/metrics/cost/quality, so the two
flagship trust features (trace grading, Production Readiness Score) were
invisible in the one public artifact. build_submission now embeds per-run
trace grades (null when the trace is span-less) and a submission-level
readiness block, so a regenerated baseline showcases them.
"""

from __future__ import annotations

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
    sub = build_submission(results, run_dir=tmp_path, task_defs={}, submitter="me")
    assert "readiness" in sub["submission"]
    r = sub["submission"]["readiness"]
    assert 0 <= r["composite"] <= 100
    # One of two passed -> correctness 50.
    assert r["correctness"] == 50.0


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
