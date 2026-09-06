from __future__ import annotations

import re
from pathlib import Path

from awb.core.subprocesses import run_shell

# Matches lines like "file.py:10:5: E501 line too long" or "file.py:10: warning"
_LINT_LINE_RE = re.compile(r".+:\d+")


async def _run_command(cmd: str, workspace: Path) -> tuple[int, str]:
    try:
        result = await run_shell(cmd, cwd=workspace, timeout=120, combine_output=True)
        if result.exit_code == 124:
            return 1, "[TIMEOUT]"
        return result.exit_code, result.stdout.decode(errors="replace")
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


async def measure_lint_issues(commands: list[str], workspace: Path) -> tuple[int, str]:
    """Return findings and distinguish absent or failed lint measurement."""
    if not commands:
        return 0, "missing"
    total = 0
    failed = False
    for cmd in commands:
        code, output = await _run_command(cmd, workspace)
        if code == 124 or (code == 127 and "not found" in output.lower()):
            failed = True
            continue
        count = _count_lines(output)
        if count == 0 and code != 0:
            count = sum(1 for line in output.splitlines() if line.strip())
        total += count
    if failed:
        return total, "failed"
    return total, "measured_findings" if total else "measured_clean"


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
