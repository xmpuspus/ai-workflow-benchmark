from __future__ import annotations

import asyncio
import re
from pathlib import Path

# Matches lines like "file.py:10:5: E501 line too long" or "file.py:10: warning"
_LINT_LINE_RE = re.compile(r".+:\d+")


async def _run_command(cmd: str, workspace: Path) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return 1, "[TIMEOUT]"
        return proc.returncode, stdout.decode(errors="replace")
    except FileNotFoundError:
        return 0, ""


def _count_lines(output: str) -> int:
    return sum(1 for line in output.splitlines() if _LINT_LINE_RE.search(line))


async def count_lint_issues(commands: list[str], workspace: Path) -> int:
    total = 0
    for cmd in commands:
        code, output = await _run_command(cmd, workspace)
        if not output.strip():
            continue
        count = _count_lines(output)
        # If regex matched nothing but command failed, fall back to non-empty line count
        if count == 0 and code != 0:
            count = sum(1 for line in output.splitlines() if line.strip())
        total += count
    return total


async def run_lint(commands: list[str], workspace: Path) -> tuple[bool, str]:
    """Run lint commands. Returns (all_clean, combined_output)."""
    if not commands:
        return True, ""

    all_clean = True
    output_parts: list[str] = []

    for cmd in commands:
        code, output = await _run_command(cmd, workspace)
        output_parts.append(f"$ {cmd}\n{output}")
        if code != 0:
            all_clean = False

    return all_clean, "\n".join(output_parts)
