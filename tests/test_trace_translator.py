"""Tests for TraceTranslator: real Claude Code stream-json -> rich trace spans.

The runner used to emit only LLM_REQUEST (and a legacy top-level tool_use) spans,
so all four grader rubrics hit their trivial-pass branches and returned 100 on
every real run. These tests pin the behavior that makes the grader actually grade:
nested tool_use blocks in assistant content become FILE_EDIT / TOOL_USE /
SHELL_COMMAND spans, and Bash exit codes are correlated from tool_result events.
"""

from __future__ import annotations

import json

from awb.trace import (
    FILE_EDIT,
    LLM_REQUEST,
    SHELL_COMMAND,
    TOOL_USE,
    TraceWriter,
    load_trace,
)
from awb.trace.grader import grade_trace
from awb.trace.translate import TraceTranslator


def _assistant(content, usage=None):
    msg = {"content": content}
    if usage is not None:
        msg["usage"] = usage
    return {"type": "assistant", "message": msg}


def _tool_use(name, tid, **input_kwargs):
    return {"type": "tool_use", "id": tid, "name": name, "input": dict(input_kwargs)}


def _user_result(tid, *, is_error=False, content="ok"):
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "is_error": is_error,
                    "content": content,
                }
            ]
        },
    }


def _drain(tmp_path, events, *, workspace_root=None, task_id="BF-001"):
    p = tmp_path / "t.trace.jsonl"
    writer = TraceWriter(p)
    tr = TraceTranslator(writer, task_id, workspace_root=workspace_root)
    for e in events:
        tr.handle(e)
    writer.close()
    return p


def test_assistant_usage_emits_llm_request_span(tmp_path):
    p = _drain(tmp_path, [_assistant([], usage={"input_tokens": 100, "output_tokens": 25})])
    spans = load_trace(p)
    assert len(spans) == 1
    assert spans[0]["span_name"] == LLM_REQUEST
    assert spans[0]["attributes"]["gen_ai.usage.input_tokens"] == 100


def test_nested_read_then_edit_emits_tool_use_and_file_edit(tmp_path):
    events = [
        _assistant(
            [
                _tool_use("Read", "t1", file_path="/ws/tests/test_x.py"),
                _tool_use("Edit", "t2", file_path="/ws/src/x.py"),
            ]
        )
    ]
    p = _drain(tmp_path, events, workspace_root="/ws")
    spans = load_trace(p)
    names = [s["span_name"] for s in spans]
    assert names == [TOOL_USE, FILE_EDIT]
    assert spans[0]["attributes"]["gen_ai.tool.name"] == "read"
    assert spans[0]["attributes"]["file.path"] == "tests/test_x.py"
    assert spans[1]["attributes"]["file.path"] == "src/x.py"
    assert spans[1]["attributes"]["file.action"] == "edit"


def test_read_tests_before_edit_grades_100_when_test_read_first(tmp_path):
    events = [
        _assistant(
            [
                _tool_use("Read", "t1", file_path="/ws/tests/test_x.py"),
                _tool_use("Write", "t2", file_path="/ws/src/x.py"),
            ]
        )
    ]
    p = _drain(tmp_path, events, workspace_root="/ws")
    assert grade_trace(p)["read_tests_before_edit"] == 100


def test_read_tests_before_edit_grades_0_when_edit_without_test_read(tmp_path):
    events = [_assistant([_tool_use("Edit", "t1", file_path="/ws/src/x.py")])]
    p = _drain(tmp_path, events, workspace_root="/ws")
    assert grade_trace(p)["read_tests_before_edit"] == 0


def test_bash_result_correlation_sets_exit_code_and_runs_verification(tmp_path):
    events = [
        _assistant([_tool_use("Edit", "t1", file_path="/ws/src/x.py")]),
        _assistant([_tool_use("Bash", "t2", command="pytest -q")]),
        _user_result("t2", is_error=False),
    ]
    p = _drain(tmp_path, events, workspace_root="/ws")
    spans = load_trace(p)
    shell = [s for s in spans if s["span_name"] == SHELL_COMMAND]
    assert len(shell) == 1
    assert shell[0]["attributes"]["shell.command"] == "pytest -q"
    assert shell[0]["attributes"]["shell.exit_code"] == 0
    # A passing test command after the edit -> verification ran
    assert grade_trace(p)["ran_verification_after_change"] == 100


def test_repeated_failing_bash_penalized(tmp_path):
    events = []
    for i in range(3):
        tid = f"b{i}"
        events.append(_assistant([_tool_use("Bash", tid, command="pytest -q")]))
        events.append(_user_result(tid, is_error=True))
    p = _drain(tmp_path, events, workspace_root="/ws")
    spans = [s for s in load_trace(p) if s["span_name"] == SHELL_COMMAND]
    assert len(spans) == 3
    assert all(s["attributes"]["shell.exit_code"] != 0 for s in spans)
    assert grade_trace(p)["no_repeated_failing_command_loop"] < 100


def test_out_of_scope_edit_detected_with_relative_paths(tmp_path):
    events = [
        _assistant(
            [
                _tool_use("Edit", "t1", file_path="/ws/src/a.py"),
                _tool_use("Edit", "t2", file_path="/ws/src/b.py"),
            ]
        )
    ]
    p = _drain(tmp_path, events, workspace_root="/ws")
    assert grade_trace(p, files_to_examine=["src/a.py"])["no_out_of_scope_edits"] < 100


def test_legacy_top_level_tool_use_still_emits_span(tmp_path):
    # Backward compat: a fake adapter that sends a top-level tool_use event.
    p = _drain(tmp_path, [{"type": "tool_use", "tool": "bash"}])
    spans = load_trace(p)
    assert len(spans) == 1
    assert spans[0]["span_name"] == TOOL_USE
    assert spans[0]["attributes"]["gen_ai.tool.name"] == "bash"


def test_handle_never_raises_on_malformed_event(tmp_path):
    # Trace persistence must never crash a benchmark run.
    p = _drain(tmp_path, [{"type": "assistant"}, {"type": "user"}, {}, {"type": "weird"}])
    assert json.loads  # sanity; file may be empty but no exception propagated
    load_trace(p)  # does not raise
