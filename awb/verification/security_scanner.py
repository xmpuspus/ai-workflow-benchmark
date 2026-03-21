from __future__ import annotations

import asyncio
import re
from pathlib import Path

_BANDIT_RE = re.compile(r">> Issue:|Severity:")
_SEMGREP_RE = re.compile(r"\d+ findings?")


async def _run_command(cmd: str, workspace: Path) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return 1, "", "[TIMEOUT]"
        return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except FileNotFoundError:
        return 0, "", ""


def _count_findings(output: str, stderr: str) -> int:
    # bandit: ">> Issue:" lines
    bandit_hits = len(_BANDIT_RE.findall(output))
    if bandit_hits:
        return bandit_hits

    # semgrep: "N findings" in output or stderr
    for text in (output, stderr):
        m = _SEMGREP_RE.search(text)
        if m:
            # extract the number
            digits = re.search(r"\d+", m.group())
            if digits:
                return int(digits.group())

    return 0


async def count_security_issues(commands: list[str], workspace: Path) -> int:
    total = 0
    for cmd in commands:
        code, stdout, stderr = await _run_command(cmd, workspace)
        count = _count_findings(stdout, stderr)
        if count == 0 and code != 0:
            # fallback: count non-empty lines from both streams
            combined = stdout + stderr
            count = sum(1 for line in combined.splitlines() if line.strip())
        total += count
    return total


async def run_security_scan(commands: list[str], workspace: Path) -> tuple[bool, str]:
    """Run security commands. Returns (all_clean, combined_output)."""
    if not commands:
        return True, ""

    all_clean = True
    output_parts: list[str] = []

    for cmd in commands:
        code, stdout, stderr = await _run_command(cmd, workspace)
        combined = stdout + (f"\n[stderr]\n{stderr}" if stderr.strip() else "")
        output_parts.append(f"$ {cmd}\n{combined}")
        if code != 0:
            all_clean = False

    return all_clean, "\n".join(output_parts)
