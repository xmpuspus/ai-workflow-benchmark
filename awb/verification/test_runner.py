from __future__ import annotations

from pathlib import Path

from awb.core.subprocesses import run_shell


async def run_tests(commands: list[str], workspace: Path) -> tuple[bool, str]:
    """Run test commands in workspace. Returns (all_passed, combined_output)."""
    if not commands:
        return True, ""

    all_passed = True
    output_parts: list[str] = []

    for cmd in commands:
        try:
            result = await run_shell(cmd, cwd=workspace, timeout=300, combine_output=True)
            if result.exit_code == 124:
                output_parts.append(f"$ {cmd}\n[TIMEOUT after 300s]\n")
                all_passed = False
                continue
            out = result.stdout.decode(errors="replace")
            output_parts.append(f"$ {cmd}\n{out}")
            if result.exit_code != 0:
                all_passed = False

        except FileNotFoundError:
            output_parts.append(f"$ {cmd}\n[command not found]\n")
            all_passed = False

    return all_passed, "\n".join(output_parts)
