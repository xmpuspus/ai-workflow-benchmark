"""Span builders for AWB trace events.

Span names map to OpenTelemetry GenAI semantic conventions where applicable:
  - LLM_REQUEST -> gen_ai.client.operation
  - TOOL_USE    -> gen_ai.tool.use
AWB-specific names (custom; documented in CHANGELOG) for everything else:
  - SHELL_COMMAND -> task.shell_command
  - FILE_EDIT     -> task.file_edit
  - TEST_RUN      -> task.test_run

Recommended attribute names follow the same convention. For LLM events:
  gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens,
  gen_ai.usage.output_tokens, gen_ai.usage.cache_read_input_tokens,
  gen_ai.usage.cache_creation_input_tokens, gen_ai.tool.name,
  gen_ai.tool.call_id.

For AWB-specific events:
  shell.command, shell.exit_code, shell.cwd
  file.path, file.action ("read" | "write" | "edit"), file.lines_added,
  file.lines_deleted
  test.framework, test.passed, test.failed, test.skipped
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

LLM_REQUEST = "gen_ai.client.operation"
TOOL_USE = "gen_ai.tool.use"
SHELL_COMMAND = "task.shell_command"
FILE_EDIT = "task.file_edit"
TEST_RUN = "task.test_run"


def new_span(
    span_name: str,
    *,
    attributes: dict | None = None,
    parent_span_id: str | None = None,
    duration_ms: int = 0,
    status: str = "ok",
    events: list[dict] | None = None,
) -> dict:
    """Build a single span dict ready to be JSONL-serialized."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "span_id": str(uuid.uuid4()),
        "parent_span_id": parent_span_id,
        "span_name": span_name,
        "duration_ms": duration_ms,
        "status": status,
        "attributes": dict(attributes or {}),
        "events": list(events or []),
    }
