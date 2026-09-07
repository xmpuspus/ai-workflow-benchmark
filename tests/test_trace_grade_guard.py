"""A span-less trace must not score a misleading 100.

grade_trace's per-rubric trivial-pass branches are legitimate inside a real
trace (e.g. an agent that genuinely made no edits). But a tool that emits no
trace at all (aider runs --no-stream, or a missing file) would otherwise be
handed 100/100/100/100. grade_trace_or_none returns None for such traces so
the export/leaderboard can show "n/a" instead of fake perfection.
"""

from __future__ import annotations

from awb.trace import LLM_REQUEST, TraceWriter, new_span
from awb.trace.grader import grade_trace_or_none


def _write(tmp, *spans):
    p = tmp / "t.trace.jsonl"
    with TraceWriter(p) as w:
        for s in spans:
            w.write(s)
    return p


def test_missing_trace_returns_none(tmp_path):
    assert grade_trace_or_none(tmp_path / "does-not-exist.jsonl") is None


def test_empty_trace_returns_none(tmp_path):
    p = tmp_path / "t.trace.jsonl"
    p.write_text("")
    assert grade_trace_or_none(p) is None


def test_only_llm_spans_returns_none(tmp_path):
    # Token spans alone carry no behavior the rubrics can grade.
    p = _write(tmp_path, new_span(LLM_REQUEST, attributes={"gen_ai.usage.input_tokens": 10}))
    assert grade_trace_or_none(p) is None


def test_trace_with_file_edit_grades(tmp_path):
    from awb.trace import FILE_EDIT

    p = _write(tmp_path, new_span(FILE_EDIT, attributes={"file.path": "src/x.py"}))
    scores = grade_trace_or_none(p)
    assert scores is not None
    # No files_to_examine passed -> context_discipline is not gradeable (needs
    # scope), but a single FILE_EDIT span makes tool_call_efficiency gradeable.
    assert set(scores) == {
        "read_tests_before_edit",
        "ran_verification_after_change",
        "no_repeated_failing_command_loop",
        "tool_call_efficiency",
    }
    assert scores["tool_call_efficiency"] == 100


def test_no_out_of_scope_treats_trailing_slash_as_directory(tmp_path):
    # files_to_examine often lists a directory like "tests/"; an edit to a file
    # under it must count as in-scope (exact-set membership would wrongly fail).
    from awb.trace import FILE_EDIT, TraceWriter, new_span
    from awb.trace.grader import grade_trace

    p = tmp_path / "dir.trace.jsonl"
    with TraceWriter(p) as w:
        w.write(new_span(FILE_EDIT, attributes={"file.path": "tests/test_extra_fields.py"}))
    scores = grade_trace(p, allowed_edit_paths=["fastapi/routing.py", "tests/"])
    assert scores["no_out_of_scope_edits"] == 100


def test_no_out_of_scope_still_flags_truly_outside_edits(tmp_path):
    from awb.trace import FILE_EDIT, TraceWriter, new_span
    from awb.trace.grader import grade_trace

    p = tmp_path / "oos.trace.jsonl"
    with TraceWriter(p) as w:
        w.write(new_span(FILE_EDIT, attributes={"file.path": "scripts/release.py"}))
    scores = grade_trace(p, allowed_edit_paths=["fastapi/routing.py", "tests/"])
    assert scores["no_out_of_scope_edits"] == 0
