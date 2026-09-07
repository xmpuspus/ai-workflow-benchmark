from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shlex
import signal
import sys
from pathlib import Path

from awb.core.config import CriterionResult, PartialCreditCriterion

log = logging.getLogger(__name__)


def _is_pytest(cmd: str) -> bool:
    return "pytest" in cmd or "python3 -m pytest" in cmd


async def _eval_single(
    criterion: PartialCreditCriterion, workspace: Path
) -> tuple[CriterionResult, str]:
    passed = False
    output = ""

    try:
        command = criterion.check
        if command.startswith("awb-oracle "):
            args = shlex.split(command)
            if len(args) != 3 or args[1] not in {"BF-001", "BF-009", "CR-007"}:
                raise ValueError("Unknown trusted oracle")
            interpreter = workspace / ".venv/bin/python"
            command = shlex.join(
                [
                    str(interpreter) if interpreter.exists() else sys.executable,
                    str(Path(__file__).with_name("task_oracles.py")),
                    *args[1:],
                ]
            )
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            check_output = stdout.decode(errors="replace")
            passed = proc.returncode == 0
            log.debug("Criterion %r: rc=%d\n%s", criterion.criterion, proc.returncode, check_output)
            output = (
                f"$ {criterion.check}\n"
                f"  criterion: {criterion.criterion}\n"
                f"  rc={proc.returncode} {'PASS' if passed else 'FAIL'}\n"
                f"{check_output}"
            )
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.communicate()
            output = f"$ {criterion.check}\n  [TIMEOUT after 60s]\n"
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.communicate()
            raise
    except FileNotFoundError:
        output = f"$ {criterion.check}\n  [command not found]\n"

    points = criterion.points if passed else 0
    result = CriterionResult(
        criterion=criterion.criterion,
        points_earned=points,
        points_possible=criterion.points,
        passed=passed,
    )
    return result, output


async def evaluate_partial_credit(
    criteria: list[PartialCreditCriterion],
    workspace: Path,
    log_dir: Path | None = None,
) -> tuple[int, int, list[CriterionResult]]:
    """Evaluate partial credit criteria. Returns (earned, max, breakdown)."""
    possible = sum(c.points for c in criteria)

    # Separate pytest criteria (share venv state) from independent ones
    parallel_criteria = [(i, c) for i, c in enumerate(criteria) if not _is_pytest(c.check)]
    sequential_criteria = [(i, c) for i, c in enumerate(criteria) if _is_pytest(c.check)]

    # Run independent criteria concurrently
    parallel_pairs = await asyncio.gather(
        *[_eval_single(c, workspace) for _, c in parallel_criteria]
    )

    # Run pytest criteria sequentially to avoid venv contention
    sequential_pairs: list[tuple[CriterionResult, str]] = []
    for _, c in sequential_criteria:
        pair = await _eval_single(c, workspace)
        sequential_pairs.append(pair)

    # Reassemble in original criteria order
    indexed: dict[int, tuple[CriterionResult, str]] = {}
    for (i, _), pair in zip(parallel_criteria, parallel_pairs, strict=True):
        indexed[i] = pair
    for (i, _), pair in zip(sequential_criteria, sequential_pairs, strict=True):
        indexed[i] = pair

    results: list[CriterionResult] = []
    output_parts: list[str] = []
    earned = 0
    for i in range(len(criteria)):
        result, output = indexed[i]
        results.append(result)
        output_parts.append(output)
        earned += result.points_earned

    if log_dir:
        log_path = log_dir / "partial_credit.log"
        log_path.write_text("\n".join(output_parts))

    return earned, possible, results
