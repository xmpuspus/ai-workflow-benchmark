from __future__ import annotations

import asyncio
from pathlib import Path


async def run_tests(commands: list[str], workspace: Path) -> tuple[bool, str]:
    """Run test commands in workspace. Returns (all_passed, combined_output)."""
    if not commands:
        return True, ""

    all_passed = True
    output_parts: list[str] = []

    for cmd in commands:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                output_parts.append(f"$ {cmd}\n[TIMEOUT after 300s]\n")
                all_passed = False
                continue

            out = stdout.decode(errors="replace")
            output_parts.append(f"$ {cmd}\n{out}")
            if proc.returncode != 0:
                all_passed = False

        except FileNotFoundError:
            output_parts.append(f"$ {cmd}\n[command not found]\n")
            all_passed = False

    return all_passed, "\n".join(output_parts)
