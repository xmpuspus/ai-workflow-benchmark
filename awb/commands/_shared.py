"""Shared CLI utilities — console instance, result loading, formatters."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def load_results_from_dirs(run_dirs: tuple[str, ...]) -> list:
    """Load RunResult objects from multiple run directories."""
    from awb.core.results import ResultRecorder

    recorder = ResultRecorder()
    all_results = []
    for d in run_dirs:
        all_results.extend(recorder.load_run(Path(d)))
    return all_results
