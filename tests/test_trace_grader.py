"""Tests for trace-based behavior grading."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from awb.commands.trace_cmd import trace
from awb.trace import (
    FILE_EDIT,
    SHELL_COMMAND,
    TEST_RUN,
    TOOL_USE,
    TraceWriter,
    new_span,
)
from awb.trace.grader import grade_trace


def _build_trace(tmp: Path, *spans: dict) -> Path:
    p = tmp / "trace.jsonl"
    with TraceWriter(p) as w:
        for s in spans:
            w.write(s)
    return p


def test_read_tests_before_edit_pass(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(
            TOOL_USE,
            attributes={"gen_ai.tool.name": "Read", "file.path": "tests/test_x.py"},
        ),
        new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["read_tests_before_edit"] == 100


def test_read_tests_before_edit_fail_when_edit_first(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["read_tests_before_edit"] == 0


def test_read_tests_trivially_passes_when_no_edits(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "src/x.py"}),
    )
    scores = grade_trace(p)
    assert scores["read_tests_before_edit"] == 100


def test_ran_verification_after_change_pass_with_test_run(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
        new_span(TEST_RUN, attributes={"test.passed": 3, "test.failed": 0}),
    )
    scores = grade_trace(p)
    assert scores["ran_verification_after_change"] == 100


def test_ran_verification_after_change_pass_with_pytest_shell(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
        new_span(
            SHELL_COMMAND,
            attributes={"shell.command": "python -m pytest tests/", "shell.exit_code": 0},
        ),
    )
    scores = grade_trace(p)
    assert scores["ran_verification_after_change"] == 100


def test_ran_verification_fail_when_no_test_after_edit(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["ran_verification_after_change"] == 0


def test_no_out_of_scope_edits_with_files_to_examine(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/a.py", "file.action": "write"}),
        new_span(FILE_EDIT, attributes={"file.path": "src/b.py", "file.action": "write"}),
    )
    scores = grade_trace(p, allowed_edit_paths=["src/a.py"])
    assert scores["no_out_of_scope_edits"] == 50


def test_no_out_of_scope_edits_perfect_when_all_in_scope(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/a.py", "file.action": "write"}),
    )
    scores = grade_trace(p, allowed_edit_paths=["src/a.py"])
    assert scores["no_out_of_scope_edits"] == 100


def test_no_out_of_scope_edits_skipped_when_no_scope_set(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/wherever.py", "file.action": "write"}),
    )
    scores = grade_trace(p)  # no files_to_examine
    assert "no_out_of_scope_edits" not in scores


def test_no_repeated_failing_command_loop_clean(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(SHELL_COMMAND, attributes={"shell.command": "ls", "shell.exit_code": 0}),
    )
    scores = grade_trace(p)
    assert scores["no_repeated_failing_command_loop"] == 100


def test_no_repeated_failing_command_loop_penalizes_three_in_a_row(tmp_path: Path):
    spans = [
        new_span(SHELL_COMMAND, attributes={"shell.command": "pytest", "shell.exit_code": 1})
        for _ in range(3)
    ]
    p = _build_trace(tmp_path, *spans)
    scores = grade_trace(p)
    assert scores["no_repeated_failing_command_loop"] < 50


def test_grade_returns_all_four_keys(tmp_path: Path):
    p = _build_trace(tmp_path)
    scores = grade_trace(p)
    assert set(scores.keys()) == {
        "read_tests_before_edit",
        "ran_verification_after_change",
        "no_repeated_failing_command_loop",
    }


def test_context_discipline_none_when_no_files_to_examine(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "src/a.py"}),
    )
    scores = grade_trace(p)  # no files_to_examine
    assert "context_discipline" not in scores


def test_context_discipline_none_when_no_read_spans(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/a.py", "file.action": "write"}),
    )
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert "context_discipline" not in scores


def test_context_discipline_perfect_within_budget(tmp_path: Path):
    # budget = max(len(files_to_examine) * 2, 5) = 5 for a single-file scope
    spans = [
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": f"f{i}.py"})
        for i in range(5)
    ]
    p = _build_trace(tmp_path, *spans)
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert scores["context_discipline"] == 100


def test_context_discipline_falls_off_beyond_budget(tmp_path: Path):
    # budget = 5, ceiling (5x budget) = 25. 15 reads is the midpoint -> 50.
    spans = [
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": f"f{i}.py"})
        for i in range(15)
    ]
    p = _build_trace(tmp_path, *spans)
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert scores["context_discipline"] == 50


def test_context_discipline_zero_at_five_times_budget(tmp_path: Path):
    spans = [
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": f"f{i}.py"})
        for i in range(25)
    ]
    p = _build_trace(tmp_path, *spans)
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert scores["context_discipline"] == 0


def test_tool_call_efficiency_none_when_no_read_or_edit_spans(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(SHELL_COMMAND, attributes={"shell.command": "ls", "shell.exit_code": 0}),
    )
    scores = grade_trace(p)
    assert "tool_call_efficiency" not in scores


def test_tool_call_efficiency_perfect_with_no_redundancy(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "a.py"}),
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "b.py"}),
        new_span(FILE_EDIT, attributes={"file.path": "c.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["tool_call_efficiency"] == 100


def test_tool_call_efficiency_penalizes_repeated_reads(tmp_path: Path):
    spans = [
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "a.py"})
        for _ in range(3)
    ]
    p = _build_trace(tmp_path, *spans)
    scores = grade_trace(p)
    # a.py read 3x -> 1 redundant event (first two reads are free) -> 100 - 20
    assert scores["tool_call_efficiency"] == 80


def test_tool_call_efficiency_penalizes_immediate_re_edit(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "x.py", "file.action": "write"}),
        new_span(FILE_EDIT, attributes={"file.path": "x.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["tool_call_efficiency"] == 80


def test_tool_call_efficiency_allows_re_edit_after_verification(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "x.py", "file.action": "write"}),
        new_span(TEST_RUN, attributes={"test.passed": 1, "test.failed": 0}),
        new_span(FILE_EDIT, attributes={"file.path": "x.py", "file.action": "write"}),
    )
    scores = grade_trace(p)
    assert scores["tool_call_efficiency"] == 100


def test_grade_returns_six_keys_when_context_and_efficiency_gradeable(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "a.py"}),
        new_span(FILE_EDIT, attributes={"file.path": "a.py", "file.action": "write"}),
    )
    scores = grade_trace(p, files_to_examine=["a.py"], allowed_edit_paths=["a.py"])
    assert set(scores.keys()) == {
        "read_tests_before_edit",
        "ran_verification_after_change",
        "no_out_of_scope_edits",
        "no_repeated_failing_command_loop",
        "context_discipline",
        "tool_call_efficiency",
    }


class TestGradeCliSixRubricColumns:
    """`awb trace grade` was extended to 6 rubrics everywhere else in v1.6
    (gap, checkup, submit); the grade table itself must show the two new
    columns rather than silently truncating a trace's own grade output."""

    def _write_run(self, run_dir: Path, task_id: str, files_to_examine: list[str]) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        with TraceWriter(run_dir / f"{task_id}.trace.jsonl") as w:
            w.write(
                new_span(TOOL_USE, attributes={"gen_ai.tool.name": "Read", "file.path": "src/x.py"})
            )
            w.write(
                new_span(FILE_EDIT, attributes={"file.path": "src/x.py", "file.action": "write"})
            )
        (run_dir / f"{task_id}.json").write_text(
            json.dumps({"task": {"files_to_examine": files_to_examine}})
        )

    def test_new_rubric_columns_appear_when_gradeable(self, tmp_path):
        self._write_run(tmp_path, "BF-001", files_to_examine=["src/x.py"])

        result = CliRunner().invoke(trace, ["grade", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "ctx_disc" in result.output
        assert "tool_eff" in result.output

    def test_new_rubric_columns_blank_when_not_gradeable(self, tmp_path):
        # No files_to_examine -> context_discipline isn't gradeable; a bare
        # single edit with no prior read makes tool_call_efficiency n/a too
        # only when there's no read/edit signal at all, so use an empty scope
        # and assert the missing column renders as a blank cell, not a crash.
        self._write_run(tmp_path, "BF-002", files_to_examine=[])

        result = CliRunner().invoke(trace, ["grade", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "ctx_disc" in result.output
