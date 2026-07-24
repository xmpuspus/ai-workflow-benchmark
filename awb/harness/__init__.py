"""Harness design scoring.

Extract testable promises from a CLAUDE.md/AGENTS.md/settings.json harness
(promises.py), statically check its structure with zero model calls
(structure.py), and join the promises against trace-graded rubric behavior
into a rule-integrity verdict (integrity.py). This is the machinery behind
`awb checkup` stage 0 and the rule-integrity table.
"""

from __future__ import annotations

from awb.harness.integrity import RuleVerdict, rule_integrity
from awb.harness.promises import HarnessInventory, HarnessPromise, extract_promises
from awb.harness.structure import StructuralIssue, check_structure

__all__ = [
    "HarnessInventory",
    "HarnessPromise",
    "RuleVerdict",
    "StructuralIssue",
    "check_structure",
    "extract_promises",
    "rule_integrity",
]
