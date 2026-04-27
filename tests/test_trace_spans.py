"""Tests for trace span builder + JSONL writer."""

from __future__ import annotations

import json
from pathlib import Path

from awb.trace import (
    FILE_EDIT,
    LLM_REQUEST,
    SHELL_COMMAND,
    TEST_RUN,
    TOOL_USE,
    TraceWriter,
    load_trace,
    new_span,
)


def test_llm_request_span_uses_otel_name():
    s = new_span(
        LLM_REQUEST,
        attributes={
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-opus-4-7",
            "gen_ai.usage.input_tokens": 1200,
            "gen_ai.usage.output_tokens": 340,
        },
    )
    assert s["span_name"] == "gen_ai.client.operation"
    assert s["attributes"]["gen_ai.system"] == "anthropic"
    assert s["attributes"]["gen_ai.request.model"] == "claude-opus-4-7"
    assert "span_id" in s
    assert "timestamp" in s
    assert s["status"] == "ok"
    assert s["events"] == []


def test_tool_use_span_uses_otel_name():
    s = new_span(TOOL_USE, attributes={"gen_ai.tool.name": "bash"})
    assert s["span_name"] == "gen_ai.tool.use"


def test_shell_command_span_uses_custom_name():
    s = new_span(
        SHELL_COMMAND,
        attributes={"shell.command": "pytest -xvs", "shell.exit_code": 0},
    )
    assert s["span_name"] == "task.shell_command"
    assert s["attributes"]["shell.exit_code"] == 0


def test_file_edit_span():
    s = new_span(
        FILE_EDIT,
        attributes={"file.path": "src/x.py", "file.action": "write"},
    )
    assert s["span_name"] == "task.file_edit"


def test_test_run_span_with_status_and_duration():
    s = new_span(
        TEST_RUN,
        attributes={"test.passed": 5, "test.failed": 1},
        duration_ms=2400,
        status="error",
    )
    assert s["span_name"] == "task.test_run"
    assert s["duration_ms"] == 2400
    assert s["status"] == "error"


def test_parent_span_id_links_child_to_parent():
    parent = new_span(LLM_REQUEST, attributes={"gen_ai.system": "anthropic"})
    child = new_span(TOOL_USE, parent_span_id=parent["span_id"])
    assert child["parent_span_id"] == parent["span_id"]


def test_writer_appends_jsonl_one_event_per_line(tmp_path: Path):
    p = tmp_path / "trace.jsonl"
    with TraceWriter(p) as w:
        w.write(new_span(SHELL_COMMAND, attributes={"shell.command": "ls"}))
        w.write(new_span(FILE_EDIT, attributes={"file.path": "x.py"}))
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_load_trace_roundtrip(tmp_path: Path):
    p = tmp_path / "trace.jsonl"
    with TraceWriter(p) as w:
        w.write(new_span(TOOL_USE, attributes={"gen_ai.tool.name": "bash"}))
        w.write(new_span(TEST_RUN, attributes={"test.passed": 5, "test.failed": 1}))
    spans = load_trace(p)
    assert len(spans) == 2
    assert spans[0]["attributes"]["gen_ai.tool.name"] == "bash"
    assert spans[1]["attributes"]["test.failed"] == 1


def test_load_trace_empty_path_returns_empty_list(tmp_path: Path):
    assert load_trace(tmp_path / "missing.jsonl") == []


def test_writer_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "deeply" / "nested" / "trace.jsonl"
    with TraceWriter(p) as w:
        w.write(new_span(SHELL_COMMAND, attributes={"shell.command": "ls"}))
    assert p.exists()
