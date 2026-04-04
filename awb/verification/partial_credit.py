from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from awb.core.config import CriterionResult, PartialCreditCriterion

log = logging.getLogger(__name__)


async def evaluate_partial_credit(
    criteria: list[PartialCreditCriterion],
    workspace: Path,
    log_dir: Path | None = None,
) -> tuple[int, int, list[CriterionResult]]:
    """Evaluate partial credit criteria. Returns (earned, max, breakdown)."""
    results: list[CriterionResult] = []
    earned = 0
    possible = 0
    output_parts: list[str] = []

    for criterion in criteria:
        possible += criterion.points
        passed = False

        try:
            proc = await asyncio.create_subprocess_shell(
                criterion.check,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
                check_output = stdout.decode(errors="replace")
                passed = proc.returncode == 0
                log.debug(
                    "Criterion %r: rc=%d\n%s", criterion.criterion, proc.returncode, check_output
                )
                output_parts.append(
                    f"$ {criterion.check}\n"
                    f"  criterion: {criterion.criterion}\n"
                    f"  rc={proc.returncode} {'PASS' if passed else 'FAIL'}\n"
                    f"{check_output}"
                )
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                output_parts.append(f"$ {criterion.check}\n  [TIMEOUT after 60s]\n")
        except FileNotFoundError:
            output_parts.append(f"$ {criterion.check}\n  [command not found]\n")

        points = criterion.points if passed else 0
        earned += points
        results.append(
            CriterionResult(
                criterion=criterion.criterion,
                points_earned=points,
                points_possible=criterion.points,
                passed=passed,
            )
        )

    if log_dir:
        log_path = log_dir / "partial_credit.log"
        log_path.write_text("\n".join(output_parts))

    return earned, possible, results
