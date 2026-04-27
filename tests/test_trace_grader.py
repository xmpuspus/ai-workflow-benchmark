"""Tests for trace-based behavior grading."""

from __future__ import annotations

from pathlib import Path

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
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert scores["no_out_of_scope_edits"] == 50


def test_no_out_of_scope_edits_perfect_when_all_in_scope(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/a.py", "file.action": "write"}),
    )
    scores = grade_trace(p, files_to_examine=["src/a.py"])
    assert scores["no_out_of_scope_edits"] == 100


def test_no_out_of_scope_edits_skipped_when_no_scope_set(tmp_path: Path):
    p = _build_trace(
        tmp_path,
        new_span(FILE_EDIT, attributes={"file.path": "src/wherever.py", "file.action": "write"}),
    )
    scores = grade_trace(p)  # no files_to_examine
    assert scores["no_out_of_scope_edits"] == 100


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
        "no_out_of_scope_edits",
        "no_repeated_failing_command_loop",
    }
