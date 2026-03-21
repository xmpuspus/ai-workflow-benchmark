"""Async timeout enforcement for benchmark runs."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class TaskTimeoutError(Exception):
    """Raised when a benchmark task exceeds its timeout."""

    def __init__(self, task_id: str, timeout_seconds: int) -> None:
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Task {task_id} timed out after {timeout_seconds}s"
        )


async def run_with_timeout(
    coro: Coroutine[Any, Any, Any],
    timeout_seconds: int,
    task_id: str = "",
) -> Any:
    """Run a coroutine with a timeout. Raises TaskTimeoutError on expiry."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except TimeoutError:
        raise TaskTimeoutError(task_id, timeout_seconds) from None
