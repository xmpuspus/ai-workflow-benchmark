from __future__ import annotations

import asyncio
from pathlib import Path

from awb.core.config import CriterionResult, PartialCreditCriterion


async def evaluate_partial_credit(
    criteria: list[PartialCreditCriterion],
    workspace: Path,
) -> tuple[int, int, list[CriterionResult]]:
    """Evaluate partial credit criteria. Returns (earned, max, breakdown)."""
    results: list[CriterionResult] = []
    earned = 0
    possible = 0

    for criterion in criteria:
        possible += criterion.points
        passed = False

        try:
            proc = await asyncio.create_subprocess_shell(
                criterion.check,
                cwd=workspace,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=60)
                passed = proc.returncode == 0
            except TimeoutError:
                proc.kill()
                await proc.communicate()
        except FileNotFoundError:
            pass

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

    return earned, possible, results
