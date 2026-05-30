"""Translate Claude Code stream-json events into rich AWB trace spans.

Claude Code emits tool calls as `tool_use` blocks *nested inside* an
`assistant` event's `message.content`, and reports their results in a later
`user` event's `tool_result` blocks. The original runner only inspected the
top-level event `type`, so it emitted nothing but LLM_REQUEST spans — which
made all four grader rubrics fall through to their trivial-pass branches and
score 100 on every real run. This translator walks the nested structure so the
grader has FILE_EDIT / SHELL_COMMAND / read-tool spans to actually grade.

Trace persistence must never crash a benchmark run, so `handle` swallows and
logs any per-event error rather than propagating it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from awb.trace.jsonl import TraceWriter
from awb.trace.spans import FILE_EDIT, LLM_REQUEST, SHELL_COMMAND, TOOL_USE, new_span

log = logging.getLogger(__name__)

# Claude Code tool names that change files, mapped to a file.action label.
_EDIT_TOOLS = {
    "edit": "edit",
    "multiedit": "edit",
    "str_replace_editor": "edit",
    "notebookedit": "edit",
    "write": "write",
    "create": "write",
}
# Tools that read a file (used by the read-tests-before-edit rubric).
_READ_TOOLS = {"read", "view", "open"}

_USAGE_ATTR_MAP = (
    ("input_tokens", "gen_ai.usage.input_tokens"),
    ("output_tokens", "gen_ai.usage.output_tokens"),
    ("cache_read_input_tokens", "gen_ai.usage.cache_read_input_tokens"),
    ("cache_creation_input_tokens", "gen_ai.usage.cache_creation_input_tokens"),
)


class TraceTranslator:
    """Stateful translator from stream events to trace spans for one task."""

    def __init__(
        self, writer: TraceWriter, task_id: str, workspace_root: Path | str | None = None
    ) -> None:
        self.writer = writer
        self.task_id = task_id
        self.workspace_root = str(workspace_root) if workspace_root else None
        # tool_use_id -> shell command, awaiting its tool_result for the exit code.
        self._pending_bash: dict[str, str] = {}

    def handle(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        try:
            etype = event.get("type", "")
            if etype == "assistant":
                self._handle_assistant(event)
            elif etype == "user":
                self._handle_user(event)
            elif etype == "tool_use":
                # Legacy / fake-adapter path: a top-level tool_use event.
                name = event.get("tool") or event.get("name") or "unknown"
                self._write(TOOL_USE, {"gen_ai.tool.name": str(name).lower()})
        except Exception as exc:  # never crash a run on trace translation
            log.debug("Trace translation failed (non-fatal): %s", exc)

    def _handle_assistant(self, event: dict) -> None:
        message = event.get("message") or {}
        usage = message.get("usage") or {}
        if isinstance(usage, dict) and (usage.get("input_tokens") or usage.get("output_tokens")):
            attrs: dict = {"gen_ai.system": "anthropic"}
            for src, dst in _USAGE_ATTR_MAP:
                if src in usage:
                    attrs[dst] = usage[src]
            self._write(LLM_REQUEST, attrs)

        content = message.get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                self._handle_tool_use_block(block)

    def _handle_tool_use_block(self, block: dict) -> None:
        name = str(block.get("name") or "unknown")
        lname = name.lower()
        tool_input = block.get("input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}

        if lname == "bash":
            command = str(tool_input.get("command", ""))
            tid = block.get("id")
            if tid:
                self._pending_bash[tid] = command
            else:
                # No id to correlate; emit immediately with unknown exit code.
                self._write(SHELL_COMMAND, {"shell.command": command, "shell.exit_code": 0})
            return

        if lname in _EDIT_TOOLS:
            self._write(
                FILE_EDIT,
                {
                    "file.path": self._rel(tool_input.get("file_path")),
                    "file.action": _EDIT_TOOLS[lname],
                },
            )
            return

        # Read / generic tools -> TOOL_USE; file.path only when present.
        attrs = {"gen_ai.tool.name": lname}
        if lname in _READ_TOOLS:
            attrs["file.path"] = self._rel(tool_input.get("file_path"))
        self._write(TOOL_USE, attrs)

    def _handle_user(self, event: dict) -> None:
        message = event.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tid = block.get("tool_use_id")
            if tid in self._pending_bash:
                command = self._pending_bash.pop(tid)
                exit_code = 1 if block.get("is_error") else 0
                self._write(SHELL_COMMAND, {"shell.command": command, "shell.exit_code": exit_code})

    def _rel(self, path: str | None) -> str:
        if not path:
            return ""
        if self.workspace_root:
            # Try both the given root and its realpath: on macOS the workspace
            # lives under /tmp (a symlink to /private/tmp), but the agent reports
            # the resolved /private/tmp path, so a literal prefix-strip misses.
            roots = [self.workspace_root.rstrip("/")]
            try:
                real = os.path.realpath(self.workspace_root).rstrip("/")
                if real not in roots:
                    roots.append(real)
            except OSError:
                pass
            for root in roots:
                if path == root:
                    return ""
                if path.startswith(root + "/"):
                    return path[len(root) + 1 :]
        return path

    def _write(self, span_name: str, attributes: dict) -> None:
        attributes = {"task.id": self.task_id, **attributes}
        self.writer.write(new_span(span_name, attributes=attributes))
