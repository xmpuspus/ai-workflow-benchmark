"""Async subprocess helpers with process-group cleanup."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


async def stop_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate the whole process group, including children after parent exit."""
    with contextlib.suppress(ProcessLookupError, OSError):
        os.killpg(proc.pid, signal.SIGTERM)
    await asyncio.sleep(0.2)
    with contextlib.suppress(ProcessLookupError, OSError):
        os.killpg(proc.pid, signal.SIGKILL)
    if proc.returncode is None:
        await proc.wait()


async def run_shell(
    command: str,
    *,
    cwd: Path,
    timeout: float,
    combine_output: bool = False,
) -> ProcessResult:
    stderr_target = asyncio.subprocess.STDOUT if combine_output else asyncio.subprocess.PIPE
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=stderr_target,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            await stop_process_group(proc)
            return ProcessResult(124, b"", b"[TIMEOUT]")
    except asyncio.CancelledError:
        await stop_process_group(proc)
        raise
    return ProcessResult(proc.returncode or 0, stdout, stderr or b"")


async def run_exec(
    *command: str,
    cwd: Path | None,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            await stop_process_group(proc)
            return ProcessResult(124, b"", b"[TIMEOUT]")
    except asyncio.CancelledError:
        await stop_process_group(proc)
        raise
    return ProcessResult(proc.returncode or 0, stdout, stderr)
