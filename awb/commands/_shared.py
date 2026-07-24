"""Shared CLI utilities, console, result loading, formatters, visual contract.

The visual contract (color constants, score_style, summary_table, headline_panel,
emit_json) is used by every awb subcommand so output looks like one tool, not
nine different dialects.

Exit code contract (project-wide, added v1.6): every analysis/probe command
that can fail meaningfully uses the same three codes, so cron/CI can branch on
exit status without reading output.
    0 = clean, ran fine, nothing to flag
    1 = real finding, drift beyond threshold, a BROKEN rule, a structural
        harness error, a measured pillar below 50, etc. (command-specific
        meaning of "finding", but always "ran fine and found a problem")
    2 = tool/environment failure, auth rejected, adapter unavailable, a
        setup/load crash, or (for --last-run consumers) no saved run to
        resolve, or an explicit run_dir/baseline path that doesn't exist.
        Distinct from "ran fine and found a problem".
Applies to checkup, drift, ab, validate, and the --last-run consumers
(gap, cost, trace grade). Keep it stable, do not repurpose a code.
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


# ----- --last-run plumbing (added v1.6) --------------------------------------
# A fixed relative path, not RESULTS_DIR-derived: the pointer must be findable
# regardless of where AWB_RESULTS_DIR points a given run's output.
_LAST_RUN_POINTER = Path("results") / ".last_run"


def save_last_run(run_dir: Path) -> None:
    """Record the most recently produced run dir for later --last-run lookup.

    Called by any command that finishes a real run (run.py's runner, checkup's
    probe) so the next gap/cost/drift/trace invocation doesn't need the run
    dir hand-copied off the terminal.
    """
    _LAST_RUN_POINTER.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_POINTER.write_text(f"{run_dir}\n")


def resolve_run_dir(arg: str | None) -> Path | None:
    """Resolve a run_dir CLI argument, falling back to the saved last run.

    None (argument omitted) or the literal "last" both mean "whatever was
    saved most recently". Returns None, never raises, when nothing has been
    saved yet, callers print their own message and exit(2).
    """
    if arg is not None and arg != "last":
        return Path(arg)
    if not _LAST_RUN_POINTER.exists():
        return None
    saved = _LAST_RUN_POINTER.read_text().strip()
    return Path(saved) if saved else None


def resolve_run_dir_or_exit(arg: str | None, fmt: str) -> Path:
    """Resolve arg via resolve_run_dir, or exit(2) with a clean message.

    Shared by every --last-run consumer (gap, drift, trace grade) so "nothing
    saved yet" and "you pointed at a path that doesn't exist" both surface as
    the same tool/environment failure (exit 2, per this module's exit-code
    contract) instead of an uncaught exception or a misleading 0/1.
    """
    resolved = resolve_run_dir(arg)
    if resolved is None:
        _print_run_dir_error(fmt, "No run directory given and no last run saved")
        sys.exit(2)
    if not resolved.exists():
        _print_run_dir_error(fmt, f"Run directory not found: {resolved}")
        sys.exit(2)
    return resolved


def _print_run_dir_error(fmt: str, message: str) -> None:
    if fmt == "json":
        emit_json({"error": message[0].lower() + message[1:]})
    else:
        console.print(f"[{BAD}]{message}[/{BAD}]")
