"""Shared CLI utilities — console, result loading, formatters, visual contract.

The visual contract (color constants, score_style, summary_table, headline_panel,
emit_json) is used by every awb subcommand so output looks like one tool, not
nine different dialects.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()

# ----- Visual contract ------------------------------------------------------
# Use these by name (OK, WARN, BAD, INFO, MUTED) anywhere in CLI output so
# color carries consistent meaning across commands. If you find yourself
# typing a raw "[red]..." literal in a command file, prefer one of these.
OK = "green"
WARN = "yellow"
BAD = "red"
INFO = "cyan"
MUTED = "dim"

# Block-bar glyphs used by capability profiles, score bars, etc.
BAR_FILLED = "█"  # solid block
BAR_EMPTY = "░"  # light shade


def score_style(score: float) -> str:
    """Map a 0-100 score to a Rich color via the project's banding rule."""
    if score >= 80:
        return OK
    if score >= 50:
        return WARN
    return BAD


def confidence_label(n: int) -> str:
    """Sample-size to confidence label used by gap / readiness / stability."""
    if n >= 20:
        return "high"
    if n >= 8:
        return "med"
    return "low"


def bar(score: float | None, width: int = 20) -> str:
    """Unicode block bar of the given width. None -> empty bar of dots."""
    if score is None:
        return "·" * width  # middle dots for n/a
    filled = max(0, min(width, int(round(score / (100.0 / width)))))
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def summary_table(
    title: str,
    columns: list[tuple[str, str]],  # [(header, justify), ...]
    rows: Iterable[Iterable[Any]],
    footer: Iterable[Any] | None = None,
) -> Table:
    """One canonical Table builder so every command looks alike."""
    t = Table(title=title, show_footer=footer is not None, header_style="bold")
    for header, justify in columns:
        t.add_column(header, justify=justify)
    rows = list(rows)
    for row in rows:
        t.add_row(*[str(c) if not isinstance(c, str) else c for c in row])
    if footer is not None:
        t.columns[0].footer = str(next(iter(footer))) if footer else ""
        # Set the rest of the footer cells if provided
        for col, val in zip(t.columns[1:], list(footer)[1:], strict=False):
            col.footer = str(val)
    return t


def headline_panel(metric: str, value: str, subtitle: str = "") -> Panel:
    """Big-number panel for the one number that matters per command."""
    body = f"[bold]{value}[/bold]"
    if subtitle:
        body += f"\n[{MUTED}]{subtitle}[/{MUTED}]"
    return Panel(body, title=metric, expand=False, border_style=INFO)


def emit_json(data: Any, indent: int = 2) -> None:
    """Print a dataclass/dict/list as JSON to stdout (--format json)."""

    def _convert(o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return {k: _convert(v) for k, v in dataclasses.asdict(o).items()}
        if isinstance(o, dict):
            return {k: _convert(v) for k, v in o.items()}
        if isinstance(o, list | tuple):
            return [_convert(x) for x in o]
        return o

    json.dump(_convert(data), sys.stdout, indent=indent, default=str)
    sys.stdout.write("\n")


# ----- Loaders --------------------------------------------------------------
def load_results_from_dirs(run_dirs: tuple[str, ...]) -> list:
    """Load RunResult objects from multiple run directories."""
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    all_results = []
    for d in run_dirs:
        all_results.extend(recorder.load_run(Path(d)))
    return all_results
