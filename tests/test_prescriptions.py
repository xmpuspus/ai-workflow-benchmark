"""Tests for prescriptive gap output (awb gap --prescribe)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from awb.analysis.prescriptions import (
    CAPABILITY_PRESCRIPTIONS,
    RUBRIC_PRESCRIPTIONS,
    Prescription,
    PrescriptionReport,
    _capability_prescriptions,
    _rubric_prescriptions,
    build_prescriptions,
)
from awb.commands.analyze import gap
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)
from awb.trace import FILE_EDIT, LLM_REQUEST, TEST_RUN, TraceWriter, new_span


def _make_task(
    task_id="BF-001",
    capabilities=None,
    files_to_examine=None,
) -> TaskDefinition:
    return TaskDefinition(
        id=task_id,
        category="bug-fix",
        title="Test task",
        difficulty="easy",
        estimated_minutes=15,
        languages=["python"],
        repo=TaskRepo(url="https://example.com", commit="abc123"),
        verification=TaskVerification(),
        constraints=TaskConstraints(),
        capabilities=capabilities or ["code_comprehension"],
        files_to_examine=files_to_examine or [],
    )


def _make_result(
    task_id="BF-001",
    tool="fake-tool",
    run_id="test-run",
    score=50,
    max_score=100,
    trace_path="",
) -> RunResult:
    return RunResult(
        task_id=task_id,
        tool=tool,
        run_id=run_id,
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(success=False, partial_credit_score=score, partial_credit_max=max_score),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
        trace_path=trace_path,
    )


def _write_trace(run_dir: Path, name: str, *spans: dict) -> str:
    p = run_dir / name
    with TraceWriter(p) as w:
        for s in spans:
            w.write(s)
    return name


class TestRubricPrescriptions:
    def test_fires_at_two_low_scoring_tasks(self):
        scores = {"read_tests_before_edit": [("BF-001", 0), ("BF-003", 20)]}
        prescriptions = _rubric_prescriptions(scores)
        assert len(prescriptions) == 1
        assert prescriptions[0].trigger == "trace:read_tests_before_edit"
        assert prescriptions[0].affected_tasks == ["BF-001", "BF-003"]
        assert prescriptions[0].evidence == ["BF-001: scored 0", "BF-003: scored 20"]
        assert prescriptions[0].severity == 2

    def test_one_low_scoring_task_does_not_fire(self):
        scores = {"read_tests_before_edit": [("BF-001", 0)]}
        assert _rubric_prescriptions(scores) == []

    def test_estimated_score_delta_is_mean_shortfall_below_threshold(self):
        scores = {"read_tests_before_edit": [("BF-001", 40), ("BF-003", 50)]}
        prescriptions = _rubric_prescriptions(scores)
        # threshold 60, mean of [40, 50] is 45 -> shortfall 15.0
        assert prescriptions[0].estimated_score_delta == pytest.approx(15.0)

    def test_threshold_boundary_exactly_60_does_not_fire(self):
        scores = {"no_out_of_scope_edits": [("BF-001", 60), ("BF-003", 60)]}
        assert _rubric_prescriptions(scores) == []

    def test_threshold_boundary_59_fires(self):
        scores = {"no_out_of_scope_edits": [("BF-001", 59), ("BF-003", 59)]}
        prescriptions = _rubric_prescriptions(scores)
        assert len(prescriptions) == 1
        assert prescriptions[0].severity == 2

    def test_unknown_rubric_name_ignored(self):
        scores = {"not_a_real_rubric": [("BF-001", 0), ("BF-003", 0)]}
        assert _rubric_prescriptions(scores) == []

    def test_snippet_is_pasted_from_table_not_regenerated(self):
        scores = {"ran_verification_after_change": [("BF-001", 0), ("BF-003", 0)]}
        prescriptions = _rubric_prescriptions(scores)
        expected = RUBRIC_PRESCRIPTIONS["ran_verification_after_change"]["snippet"]
        assert prescriptions[0].snippet == expected

    def test_all_six_rubric_names_have_prescriptions(self):
        assert set(RUBRIC_PRESCRIPTIONS.keys()) == {
            "read_tests_before_edit",
            "ran_verification_after_change",
            "no_out_of_scope_edits",
            "no_repeated_failing_command_loop",
            "context_discipline",
            "tool_call_efficiency",
        }


class TestCapabilityPrescriptions:
    def test_fires_below_threshold_with_two_tasks(self):
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["security_awareness"]),
            "BF-003": _make_task("BF-003", capabilities=["security_awareness"]),
        }
        results = [
            _make_result("BF-001", score=40, max_score=100),
            _make_result("BF-003", score=50, max_score=100),
        ]
        prescriptions = _capability_prescriptions(results, task_defs, threshold=60)
        assert len(prescriptions) == 1
        assert prescriptions[0].trigger == "capability:security_awareness"
        assert prescriptions[0].affected_tasks == ["BF-001", "BF-003"]
        assert prescriptions[0].evidence == ["BF-001: scored 40.0", "BF-003: scored 50.0"]
        # threshold 60, mean of [40.0, 50.0] is 45.0 -> shortfall 15.0
        assert prescriptions[0].estimated_score_delta == pytest.approx(15.0)

    def test_single_task_does_not_fire(self):
        task_defs = {"BF-001": _make_task("BF-001", capabilities=["security_awareness"])}
        results = [_make_result("BF-001", score=10, max_score=100)]
        assert _capability_prescriptions(results, task_defs, threshold=60) == []

    def test_threshold_boundary_exactly_60_does_not_fire(self):
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["security_awareness"]),
            "BF-003": _make_task("BF-003", capabilities=["security_awareness"]),
        }
        results = [
            _make_result("BF-001", score=60, max_score=100),
            _make_result("BF-003", score=60, max_score=100),
        ]
        assert _capability_prescriptions(results, task_defs, threshold=60) == []

    def test_threshold_boundary_59_fires(self):
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["security_awareness"]),
            "BF-003": _make_task("BF-003", capabilities=["security_awareness"]),
        }
        results = [
            _make_result("BF-001", score=59, max_score=100),
            _make_result("BF-003", score=59, max_score=100),
        ]
        prescriptions = _capability_prescriptions(results, task_defs, threshold=60)
        assert len(prescriptions) == 1
        # Severity is the count of below-threshold tasks (same unit as
        # rubric prescriptions so the combined sort is comparable).
        assert prescriptions[0].severity == 2

    def test_capability_without_prescription_entry_never_fires(self):
        # a made-up capability name has no entry in CAPABILITY_PRESCRIPTIONS
        assert "not_a_real_capability" not in CAPABILITY_PRESCRIPTIONS
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["not_a_real_capability"]),
            "BF-003": _make_task("BF-003", capabilities=["not_a_real_capability"]),
        }
        results = [
            _make_result("BF-001", score=10, max_score=100),
            _make_result("BF-003", score=10, max_score=100),
        ]
        assert _capability_prescriptions(results, task_defs, threshold=60) == []

    def test_all_eleven_capabilities_have_prescriptions(self):
        assert set(CAPABILITY_PRESCRIPTIONS.keys()) == {
            "code_comprehension",
            "bug_diagnosis",
            "multi_file_reasoning",
            "framework_knowledge",
            "test_writing",
            "refactoring_discipline",
            "security_awareness",
            "completeness_tracking",
            "convention_adherence",
            "context_discovery",
            "security_methodology",
        }


class TestBuildPrescriptionsTraceGrading:
    def test_missing_trace_path_counted_as_missing(self, tmp_path: Path):
        task_defs = {"BF-001": _make_task("BF-001")}
        results = [_make_result("BF-001", trace_path="")]
        report = build_prescriptions(results, task_defs, tmp_path)
        assert report.n_traces_missing == 1
        assert report.n_traces_graded == 0

    def test_trace_file_absent_on_disk_counted_as_missing(self, tmp_path: Path):
        task_defs = {"BF-001": _make_task("BF-001")}
        results = [_make_result("BF-001", trace_path="nope.trace.jsonl")]
        report = build_prescriptions(results, task_defs, tmp_path)
        assert report.n_traces_missing == 1
        assert report.n_traces_graded == 0

    def test_span_less_trace_counted_as_missing_never_graded(self, tmp_path: Path):
        name = _write_trace(tmp_path, "BF-001.trace.jsonl")  # zero spans
        task_defs = {"BF-001": _make_task("BF-001")}
        results = [_make_result("BF-001", trace_path=name)]
        report = build_prescriptions(results, task_defs, tmp_path)
        assert report.n_traces_missing == 1
        assert report.n_traces_graded == 0

    def test_llm_only_trace_counted_as_missing(self, tmp_path: Path):
        name = _write_trace(
            tmp_path,
            "BF-001.trace.jsonl",
            new_span(LLM_REQUEST, attributes={"gen_ai.usage.input_tokens": 10}),
        )
        task_defs = {"BF-001": _make_task("BF-001")}
        results = [_make_result("BF-001", trace_path=name)]
        report = build_prescriptions(results, task_defs, tmp_path)
        assert report.n_traces_missing == 1
        assert report.n_traces_graded == 0

    def test_gradeable_trace_counted_as_graded(self, tmp_path: Path):
        name = _write_trace(
            tmp_path,
            "BF-001.trace.jsonl",
            new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
        )
        task_defs = {"BF-001": _make_task("BF-001")}
        results = [_make_result("BF-001", trace_path=name)]
        report = build_prescriptions(results, task_defs, tmp_path)
        assert report.n_traces_graded == 1
        assert report.n_traces_missing == 0

    def test_two_tasks_scoring_zero_on_read_tests_before_edit_fires(self, tmp_path: Path):
        task_defs = {"BF-001": _make_task("BF-001"), "BF-003": _make_task("BF-003")}
        results = []
        for tid in ("BF-001", "BF-003"):
            name = _write_trace(
                tmp_path,
                f"{tid}.trace.jsonl",
                new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
            )
            results.append(_make_result(tid, trace_path=name))
        report = build_prescriptions(results, task_defs, tmp_path)
        triggers = [p.trigger for p in report.prescriptions]
        assert "trace:read_tests_before_edit" in triggers


class TestSorting:
    def test_prescriptions_sorted_most_severe_first(self):
        scores = {
            "read_tests_before_edit": [("BF-001", 0), ("BF-002", 0)],  # severity 2
            "ran_verification_after_change": [
                ("BF-003", 0),
                ("BF-004", 0),
                ("BF-005", 0),
            ],  # severity 3
        }
        prescriptions = _rubric_prescriptions(scores)
        prescriptions.sort(key=lambda p: -p.severity)
        assert prescriptions[0].severity >= prescriptions[1].severity
        assert prescriptions[0].trigger == "trace:ran_verification_after_change"

    def test_build_prescriptions_report_sorted(self, tmp_path: Path):
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["security_awareness"]),
            "BF-003": _make_task("BF-003", capabilities=["security_awareness"]),
            "BF-004": _make_task("BF-004"),
            "BF-005": _make_task("BF-005"),
        }
        results = [
            _make_result("BF-001", score=1, max_score=100),
            _make_result("BF-003", score=1, max_score=100),
        ]
        for tid in ("BF-004", "BF-005"):
            name = _write_trace(
                tmp_path,
                f"{tid}.trace.jsonl",
                new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
            )
            results.append(_make_result(tid, trace_path=name))

        report = build_prescriptions(results, task_defs, tmp_path)
        severities = [p.severity for p in report.prescriptions]
        assert severities == sorted(severities, reverse=True)

    def test_sorts_by_delta_within_equal_severity(self, tmp_path: Path):
        # Both capabilities fire with severity 2 (2 low tasks each), but
        # completeness_tracking's mean score (10) is farther below the 60
        # threshold than security_awareness's (45), so it should sort first.
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["security_awareness"]),
            "BF-003": _make_task("BF-003", capabilities=["security_awareness"]),
            "BF-004": _make_task("BF-004", capabilities=["completeness_tracking"]),
            "BF-005": _make_task("BF-005", capabilities=["completeness_tracking"]),
        }
        results = [
            _make_result("BF-001", score=40, max_score=100),
            _make_result("BF-003", score=50, max_score=100),
            _make_result("BF-004", score=10, max_score=100),
            _make_result("BF-005", score=10, max_score=100),
        ]
        report = build_prescriptions(results, task_defs, tmp_path)
        triggers = [p.trigger for p in report.prescriptions]
        assert triggers.index("capability:completeness_tracking") < triggers.index(
            "capability:security_awareness"
        )


class TestPrescriptionDataclasses:
    def test_prescription_report_defaults(self):
        report = PrescriptionReport(tool="claude-code")
        assert report.prescriptions == []
        assert report.n_traces_graded == 0
        assert report.n_traces_missing == 0

    def test_prescription_report_carries_the_non_additivity_caveat(self):
        report = PrescriptionReport(tool="claude-code")
        assert report.caveat == (
            "Impact estimates are independent; applying several fixes will not sum cleanly."
        )

    def test_prescription_fields(self):
        p = Prescription(
            id="rubric-x",
            trigger="trace:x",
            evidence=["BF-001: scored 0"],
            affected_tasks=["BF-001"],
            severity=1,
            snippet="## X\n",
            rationale="because",
        )
        assert p.id == "rubric-x"
        assert p.estimated_score_delta is None

    def test_prescription_estimated_score_delta_accepts_explicit_value(self):
        p = Prescription(
            id="rubric-x",
            trigger="trace:x",
            evidence=["BF-001: scored 0"],
            affected_tasks=["BF-001"],
            severity=1,
            snippet="## X\n",
            rationale="because",
            estimated_score_delta=15.0,
        )
        assert p.estimated_score_delta == pytest.approx(15.0)


def _real_task_pair():
    from awb.core.task_loader import load_all_tasks

    tasks = load_all_tasks()
    candidates = [
        t for t in tasks if t.files_to_examine and not t.files_to_examine[0].endswith("/")
    ]
    return candidates[0], candidates[1]


def _build_cli_run_dir(run_dir: Path) -> None:
    """Two real tasks, both scoring 0 on read_tests_before_edit."""
    task_a, task_b = _real_task_pair()
    for task in (task_a, task_b):
        trace_name = f"{task.id}_faketool.trace.jsonl"
        with TraceWriter(run_dir / trace_name) as w:
            w.write(
                new_span(
                    FILE_EDIT,
                    attributes={"file.path": task.files_to_examine[0], "file.action": "write"},
                )
            )
            w.write(new_span(TEST_RUN, attributes={"test.passed": 1, "test.failed": 0}))
        result = RunResult(
            task_id=task.id,
            tool="faketool",
            run_id="run1",
            timestamp="2026-01-01T00:00:00Z",
            outcome=RunOutcome(success=False, partial_credit_score=40, partial_credit_max=100),
            metrics=RunMetrics(),
            cost=RunCost(),
            quality=RunQuality(),
            environment=RunEnvironment(os="test", hardware="test"),
            trace_path=trace_name,
        )
        data = result.to_dict()
        (run_dir / f"{task.id}_faketool.json").write_text(json.dumps(data))


class TestGapPrescribeCli:
    def test_prescribe_text_contains_snippet(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir), "--prescribe"])
        assert result.exit_code == 0, result.output
        assert "Prescriptions" in result.output
        assert "Read Tests Before Editing" in result.output

    def test_prescribe_text_renders_impact_estimate_and_caveat(self, tmp_path: Path):
        """The impact-estimate line and its non-additivity caveat are only
        pinned today via checkup_cmd.py's analogous 'Top fixes' block (see
        test_checkup.py::test_top_fixes_include_rule_integrity_escalation_
        when_broken asserting 'not additive'); gap --prescribe renders the
        same fields through a different call site with no regression test."""
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir), "--prescribe"])
        assert result.exit_code == 0, result.output
        assert "est. +" in result.output
        assert "Impact estimates are independent" in result.output
        assert "sum cleanly" in result.output

    def test_prescribe_json_includes_prescriptions_key(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir), "--format", "json", "--prescribe"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "prescriptions" in data
        triggers = [p["trigger"] for p in data["prescriptions"]["prescriptions"]]
        assert "trace:read_tests_before_edit" in triggers

    def test_without_prescribe_has_no_prescriptions_section(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir)])
        assert result.exit_code == 0, result.output
        assert "Prescriptions" not in result.output

    def test_prescribe_is_purely_additive_when_no_top_fix_clause_fires(
        self, tmp_path: Path, monkeypatch
    ):
        """--prescribe must not change anything that renders before the
        'Prescriptions (' marker. The one documented exception is the verdict
        line's 'Top fix:' clause (see TestGapVerdictLine.
        test_top_fix_clause_appended_when_prescribe_fires), which only fires
        when a prescription is actually fired - so a single-task run (too few
        data points for any prescription to fire) makes the additive claim
        exactly testable: the two outputs must be byte-identical up to the
        Prescriptions section."""
        task_defs = [_make_task("BF-001", capabilities=["security_awareness"])]
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda: task_defs)
        run_dir = tmp_path / "run1"
        _write_result_json(run_dir, "BF-001", score=90)

        plain = CliRunner().invoke(gap, [str(run_dir)])
        prescribed = CliRunner().invoke(gap, [str(run_dir), "--prescribe"])
        assert plain.exit_code == 0, plain.output
        assert prescribed.exit_code == 0, prescribed.output

        marker = "\nPrescriptions ("
        assert marker in prescribed.output
        prescribed_head = prescribed.output.split(marker)[0]
        assert prescribed_head == plain.output

    def test_without_prescribe_json_has_no_prescriptions_key(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir), "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "prescriptions" not in data


def _write_result_json(run_dir: Path, task_id: str, score: float, tool: str = "fake-tool") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(
        task_id=task_id,
        tool=tool,
        run_id=run_dir.name,
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(success=False, partial_credit_score=score, partial_credit_max=100),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
    )
    (run_dir / f"{task_id}_{tool}.json").write_text(json.dumps(result.to_dict()))


class TestGapVerdictLine:
    """`awb gap` names the worst capability before the Capability Profile
    section (v1.6 design: one honest sentence up front, ai-workflow-benchmark
    docs/superpowers/plans/2026-07-23-awb-v16-harness-design-score.md)."""

    def _setup(self, tmp_path, monkeypatch):
        task_defs = [
            _make_task("BF-001", capabilities=["security_awareness"]),
            _make_task("BF-003", capabilities=["security_awareness"]),
        ]
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda: task_defs)
        run_dir = tmp_path / "run1"
        _write_result_json(run_dir, "BF-001", score=30)
        _write_result_json(run_dir, "BF-003", score=50)
        return run_dir

    def test_names_worst_capability_with_score_and_task_count(self, tmp_path, monkeypatch):
        run_dir = self._setup(tmp_path, monkeypatch)

        result = CliRunner().invoke(gap, [str(run_dir)])
        assert result.exit_code == 0, result.output
        # mean(30, 50) == 40; RunCost() defaults to zero spend so the derived
        # cost_discipline capability scores near-perfect and never wins "worst".
        assert "Biggest gap: security_awareness 40/100 across 2 tasks." in result.output

    def test_verdict_line_appears_before_capability_profile_section(self, tmp_path, monkeypatch):
        run_dir = self._setup(tmp_path, monkeypatch)

        result = CliRunner().invoke(gap, [str(run_dir)])
        assert result.exit_code == 0, result.output
        assert result.output.index("Biggest gap") < result.output.index("Capability Profile")

    def test_no_top_fix_clause_without_prescribe(self, tmp_path, monkeypatch):
        run_dir = self._setup(tmp_path, monkeypatch)

        result = CliRunner().invoke(gap, [str(run_dir)])
        assert result.exit_code == 0, result.output
        assert "Top fix:" not in result.output

    def test_top_fix_clause_appended_when_prescribe_fires(self, tmp_path, monkeypatch):
        run_dir = self._setup(tmp_path, monkeypatch)

        result = CliRunner().invoke(gap, [str(run_dir), "--prescribe"])
        assert result.exit_code == 0, result.output
        # Both tasks score below CAPABILITY_SCORE_THRESHOLD (60), so the
        # security_awareness prescription fires and is the only (= highest
        # severity) one in the report. Assert as two substrings, not one
        # long span, since Rich word-wraps long lines at console width.
        assert "Biggest gap: security_awareness 40/100 across 2 tasks." in result.output
        assert "Top fix: Security" in result.output
        assert "Checklist." in result.output

    def test_no_verdict_line_json_format_unaffected(self, tmp_path, monkeypatch):
        """The verdict line is text-rendering only; JSON output is untouched."""
        run_dir = self._setup(tmp_path, monkeypatch)

        result = CliRunner().invoke(gap, [str(run_dir), "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "verdict" not in data
        assert "Biggest gap" not in result.output
