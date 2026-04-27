"""Append-only JSONL writer for trace events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO


class TraceWriter:
    """Append spans to a JSONL file, one event per line.

    Use as a context manager so the file handle is always closed cleanly:

        with TraceWriter(path) as w:
            w.write(new_span(SHELL_COMMAND, attributes={"shell.command": "ls"}))
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: IO[str] | None = None

    def write(self, span: dict) -> None:
        if self._fh is None:
            self._fh = self.path.open("a")
        self._fh.write(json.dumps(span) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def load_trace(path: Path) -> list[dict]:
    """Load every span from a trace.jsonl file. Returns [] if missing."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
