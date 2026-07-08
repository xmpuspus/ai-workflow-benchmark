"""Tests for prescriptive gap output (awb gap --prescribe)."""

from __future__ import annotations

import json
from pathlib import Path

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

    def test_all_four_rubric_names_have_prescriptions(self):
        assert set(RUBRIC_PRESCRIPTIONS.keys()) == {
            "read_tests_before_edit",
            "ran_verification_after_change",
            "no_out_of_scope_edits",
            "no_repeated_failing_command_loop",
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
        assert prescriptions[0].severity == 1

    def test_capability_without_prescription_entry_never_fires(self):
        # code_comprehension has no entry in CAPABILITY_PRESCRIPTIONS
        assert "code_comprehension" not in CAPABILITY_PRESCRIPTIONS
        task_defs = {
            "BF-001": _make_task("BF-001", capabilities=["code_comprehension"]),
            "BF-003": _make_task("BF-003", capabilities=["code_comprehension"]),
        }
        results = [
            _make_result("BF-001", score=10, max_score=100),
            _make_result("BF-003", score=10, max_score=100),
        ]
        assert _capability_prescriptions(results, task_defs, threshold=60) == []

    def test_all_four_capabilities_have_prescriptions(self):
        assert set(CAPABILITY_PRESCRIPTIONS.keys()) == {
            "completeness_tracking",
            "convention_adherence",
            "refactoring_discipline",
            "security_awareness",
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


class TestPrescriptionDataclasses:
    def test_prescription_report_defaults(self):
        report = PrescriptionReport(tool="claude-code")
        assert report.prescriptions == []
        assert report.n_traces_graded == 0
        assert report.n_traces_missing == 0

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

    def test_without_prescribe_json_has_no_prescriptions_key(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        _build_cli_run_dir(run_dir)

        runner = CliRunner()
        result = runner.invoke(gap, [str(run_dir), "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "prescriptions" not in data
