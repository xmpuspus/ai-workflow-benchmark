"""AWB trace artifact: OTel-aligned span schema + JSONL persistence."""

from awb.trace.jsonl import TraceWriter, load_trace
from awb.trace.spans import (
    FILE_EDIT,
    LLM_REQUEST,
    SHELL_COMMAND,
    TEST_RUN,
    TOOL_USE,
    new_span,
)

__all__ = [
    "FILE_EDIT",
    "LLM_REQUEST",
    "SHELL_COMMAND",
    "TEST_RUN",
    "TOOL_USE",
    "TraceWriter",
    "load_trace",
    "new_span",
]
