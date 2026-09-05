"""Evidence collection for reviewing candidate benchmark tasks.

These helpers deliberately produce review records only. A reviewer must decide
whether a candidate joins a holdout after inspecting the recorded evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from awb.core.task_loader import load_task
from awb.verification.partial_credit import evaluate_partial_credit

_UNCONDITIONAL_CREDIT = re.compile(r"(?:;|\|\|)\s*true\s*$")


def task_definition_hash(path: Path) -> str:
    """Return the exact task-definition identity used for review evidence."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_path(task_definition: Path) -> Path:
    return task_definition.with_suffix(".review.json")


def _load_mapping(path: Path) -> dict[str, Any] | None:
    try:
        loaded = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _has_valid_controls(review: dict[str, Any] | None, definition_hash: str) -> bool:
    if not isinstance(review, dict) or review.get("task_definition_hash") != definition_hash:
        return False
    controls = review.get("controls")
    if not isinstance(controls, dict):
        return False
    expected = {"gold": 100, "noop": 0, "mutation": 0}
    return all(
        isinstance(controls.get(name), dict) and controls[name].get("percent") == score
        for name, score in expected.items()
    )


def audit_tasks(tasks_dir: Path) -> dict[str, Any]:
    """Inventory task definitions and evidence gaps without declaring admission."""
    findings: list[dict[str, Any]] = []
    for path in sorted(p for p in tasks_dir.rglob("*.yaml") if not p.name.startswith("_")):
        raw = _load_mapping(path)
        entry: dict[str, Any] = {
            "path": str(path),
            "task_id": raw.get("id") if raw else None,
            "review_status": "unreviewed",
            "findings": [],
        }
        if raw is None:
            entry["findings"].append("invalid_task_definition")
            findings.append(entry)
            continue

        verification = raw.get("verification")
        criteria = verification.get("partial_credit", []) if isinstance(verification, dict) else []
        unconditional = [
            criterion.get("criterion", "unnamed criterion")
            for criterion in criteria
            if isinstance(criterion, dict)
            and isinstance(criterion.get("check"), str)
            and _UNCONDITIONAL_CREDIT.search(criterion["check"])
        ]
        if unconditional:
            entry["findings"].append("unconditional_credit")
            entry["unconditional_criteria"] = unconditional

        if not isinstance(raw.get("provenance"), dict):
            entry["findings"].append("missing_provenance")

        review_path = _review_path(path)
        review = _load_json(review_path)
        try:
            definition_hash = task_definition_hash(path)
        except OSError:
            definition_hash = ""
        if not _has_valid_controls(review, definition_hash):
            entry["findings"].append("missing_independent_controls")
        findings.append(entry)

    counts = {
        "unconditional_credit": sum(
            "unconditional_credit" in item["findings"] for item in findings
        ),
        "missing_independent_controls": sum(
            "missing_independent_controls" in item["findings"] for item in findings
        ),
        "missing_provenance": sum("missing_provenance" in item["findings"] for item in findings),
        "invalid_task_definition": sum(
            "invalid_task_definition" in item["findings"] for item in findings
        ),
        "reviewed": 0,
    }
    return {
        "status": "review_required",
        "admission": "not_admitted",
        "tasks_scanned": len(findings),
        "counts": counts,
        "findings": findings,
        "next_step": "Run awb task controls on local gold, noop, and mutation workspaces.",
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _control_result(task_definition: Path, workspace: Path) -> dict[str, Any]:
    task = load_task(task_definition)
    earned, possible, breakdown = asyncio.run(
        evaluate_partial_credit(task.verification.partial_credit, workspace)
    )
    percent = 0 if possible == 0 else earned * 100 / possible
    return {
        "workspace": str(workspace),
        "earned": earned,
        "possible": possible,
        "percent": percent,
        "criteria": [
            {
                "criterion": result.criterion,
                "passed": result.passed,
                "points_earned": result.points_earned,
                "points_possible": result.points_possible,
            }
            for result in breakdown
        ],
    }


def run_control_protocol(
    task_definition: Path,
    gold_workspace: Path,
    noop_workspace: Path,
    mutation_workspace: Path,
    review_output: Path | None = None,
) -> dict[str, Any]:
    """Run trusted task criteria against explicit local control workspaces."""
    controls = {
        "gold": _control_result(task_definition, gold_workspace),
        "noop": _control_result(task_definition, noop_workspace),
        "mutation": _control_result(task_definition, mutation_workspace),
    }
    expected = {"gold": 100, "noop": 0, "mutation": 0}
    complete = all(controls[name]["percent"] == score for name, score in expected.items())
    evidence = {
        "status": "review_evidence_ready" if complete else "review_required",
        "admission": "not_admitted",
        "task_definition": str(task_definition),
        "task_definition_hash": task_definition_hash(task_definition),
        "controls": controls,
        "requirements": {
            "gold_percent": 100,
            "noop_percent": 0,
            "mutation_percent": 0,
        },
        "next_step": (
            "Inspect the oracle and controls before any separate holdout admission decision."
        ),
    }
    output = review_output or _review_path(task_definition)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    evidence["review_output"] = str(output)
    return evidence


def create_failure_candidate(
    result_path: Path,
    out_dir: Path,
    description: str,
    oracle_review: str,
    task_definition: Path | None = None,
) -> dict[str, Any]:
    """Create a review-only candidate record from one saved result artifact."""
    result = _load_json(result_path)
    if result is None:
        raise ValueError(f"Could not read a JSON result from {result_path}")
    task_id = str(result.get("task_id") or "candidate")
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = out_dir / f"{task_id}.candidate.json"
    review_path = out_dir / f"{task_id}.review.json"
    candidate = {
        "status": "candidate",
        "admission": "not_admitted",
        "source_result": str(result_path),
        "task_id": task_id,
        "description": description,
        "oracle_review": oracle_review,
        "result": result,
    }
    review: dict[str, Any] = {
        "status": "candidate",
        "admission": "not_admitted",
        "description": description,
        "oracle_review": oracle_review,
        "source_result": str(result_path),
        "next_step": "Review the candidate, oracle, provenance, and controls before admission.",
    }
    if task_definition is not None:
        task_raw = _load_mapping(task_definition)
        if task_raw is None:
            raise ValueError(f"Could not read task definition from {task_definition}")
        review["task_definition"] = str(task_definition)
        review["task_definition_hash"] = task_definition_hash(task_definition)
        review["task_id"] = task_raw.get("id", task_id)
        review["task_repo"] = task_raw.get("repo")
        review["task_provenance"] = task_raw.get("provenance")
        candidate["task_definition_hash"] = review["task_definition_hash"]
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n")
    review_path.write_text(json.dumps(review, indent=2) + "\n")
    return {
        "status": "candidate",
        "admission": "not_admitted",
        "candidate_path": str(candidate_path),
        "review_path": str(review_path),
    }
