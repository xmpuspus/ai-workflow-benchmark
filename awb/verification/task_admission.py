"""Evidence collection for reviewing candidate benchmark tasks.

These helpers deliberately produce review records only. A reviewer must decide
whether a candidate joins a holdout after inspecting the recorded evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from awb.core.task_loader import load_task, validate_task_yaml
from awb.verification.partial_credit import evaluate_partial_credit

_UNCONDITIONAL_CREDIT = re.compile(r"(?:;|\|\|)\s*true\s*$")
_CONTROL_EXPECTED = {"gold": 100, "noop": 0, "mutation": 0}
_EVALUATOR = {"name": "awb.verification.partial_credit", "version": "1"}
_RECEIPT_PROFILE = {
    "algorithm": "sha256",
    "scope": "control_evidence",
    "authentication": "none",
}


def task_definition_hash(path: Path) -> str:
    """Return the exact task-definition identity used for review evidence."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_path(task_definition: Path) -> Path:
    return task_definition.with_suffix(".review.json")


def _admission_path(task_definition: Path) -> Path:
    return task_definition.with_suffix(".admission.json")


def _load_mapping(path: Path) -> dict[str, Any] | None:
    try:
        loaded = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _has_valid_controls(review: dict[str, Any] | None, definition_hash: str) -> bool:
    if not isinstance(review, dict) or review.get("task_definition_hash") != definition_hash:
        return False
    if review.get("status") != "review_evidence_ready" or review.get("admission") != "not_admitted":
        return False
    if review.get("protocol_version") != 1 or review.get("evaluator") != _EVALUATOR:
        return False
    controls = review.get("controls")
    requirements = review.get("requirements")
    if not isinstance(controls, dict) or requirements != {
        "gold_percent": 100,
        "noop_percent": 0,
        "mutation_percent": 0,
    }:
        return False
    if set(controls) != set(_CONTROL_EXPECTED):
        return False
    for name, score in _CONTROL_EXPECTED.items():
        control = controls.get(name)
        if not isinstance(control, dict) or control.get("percent") != score:
            return False
        earned, possible = control.get("earned"), control.get("possible")
        if (
            isinstance(earned, bool)
            or isinstance(possible, bool)
            or not isinstance(earned, int | float)
            or not isinstance(possible, int | float)
            or not math.isfinite(earned)
            or not math.isfinite(possible)
            or possible <= 0
            or earned < 0
            or earned > possible
            or not math.isclose(100 * earned / possible, score)
        ):
            return False
        if not isinstance(control.get("workspace_hash"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", control["workspace_hash"]
        ):
            return False
        criteria = control.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            return False
        criterion_earned = 0.0
        criterion_possible = 0.0
        for criterion in criteria:
            if not isinstance(criterion, dict):
                return False
            points_earned = criterion.get("points_earned")
            points_possible = criterion.get("points_possible")
            passed = criterion.get("passed")
            if (
                not isinstance(criterion.get("criterion"), str)
                or not criterion["criterion"]
                or isinstance(points_earned, bool)
                or isinstance(points_possible, bool)
                or not isinstance(points_earned, int | float)
                or not isinstance(points_possible, int | float)
                or not math.isfinite(points_earned)
                or not math.isfinite(points_possible)
                or points_possible <= 0
                or points_earned not in {0, points_possible}
                or type(passed) is not bool
                or passed != (points_earned == points_possible)
            ):
                return False
            criterion_earned += points_earned
            criterion_possible += points_possible
        if not math.isclose(criterion_earned, earned) or not math.isclose(
            criterion_possible, possible
        ):
            return False
    receipt = review.get("receipt_sha256")
    receipt_detail = review.get("receipt")
    return (
        isinstance(receipt, str)
        and re.fullmatch(r"[0-9a-f]{64}", receipt) is not None
        and receipt == _receipt_hash(review)
        and isinstance(receipt_detail, dict)
        and {key: receipt_detail.get(key) for key in _RECEIPT_PROFILE} == _RECEIPT_PROFILE
        and receipt_detail.get("sha256") == receipt
        and set(receipt_detail) == {*_RECEIPT_PROFILE, "sha256"}
    )


def validate_control_review(task_definition: Path) -> bool:
    """Check structure and checksum consistency; this does not authenticate a reviewer."""
    try:
        review_path = _review_path(task_definition)
        if task_definition.is_symlink() or review_path.is_symlink():
            return False
        return _has_valid_controls(_load_json(review_path), task_definition_hash(task_definition))
    except OSError:
        return False


def validate_holdout_admission(task_definition: Path) -> bool:
    """Validate an unauthenticated operator declaration for separate holdout admission."""
    try:
        review_path = _review_path(task_definition)
        admission_path = _admission_path(task_definition)
        if task_definition.is_symlink() or review_path.is_symlink() or admission_path.is_symlink():
            return False
        definition_hash = task_definition_hash(task_definition)
        review = _load_json(review_path)
        if not _has_valid_controls(review, definition_hash):
            return False
        admission = _load_json(admission_path)
        if not isinstance(admission, dict):
            return False
        reviewed_by = admission.get("reviewed_by")
        contamination_review = admission.get("contamination_review")
        reviewed_at = admission.get("reviewed_at")
        if not isinstance(reviewed_at, str):
            return False
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        return (
            admission.get("admission") == "holdout"
            and admission.get("task_definition_hash") == definition_hash
            and admission.get("control_receipt_sha256") == review.get("receipt_sha256")
            and isinstance(reviewed_by, str)
            and bool(reviewed_by.strip())
            and timestamp.tzinfo is not None
            and admission.get("independent_oracle_review") is True
            and isinstance(contamination_review, str)
            and bool(contamination_review.strip())
        )
    except (OSError, ValueError):
        return False


def _receipt_hash(review: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in review.items() if key not in {"receipt_sha256", "receipt"}
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _workspace_hash(workspace: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in workspace.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(workspace).as_posix().encode()
        hasher.update(relative)
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(path.read_bytes()).digest())
    return hasher.hexdigest()


def _validate_control_workspace(workspace: Path) -> None:
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError(f"Control workspace is missing or is a symlink: {workspace}")
    root = workspace.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Control workspace contains a symlink: {path.relative_to(root)}")
        try:
            path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise ValueError("Control workspace entry resolves outside its root") from exc


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

        schema_errors = validate_task_yaml(path)
        if schema_errors:
            entry["findings"].append("schema_validation_failed")

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

        provenance = raw.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("source_pr_url"):
            entry["findings"].append("missing_provenance")
        repo = raw.get("repo")
        commit = repo.get("commit") if isinstance(repo, dict) else ""
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            entry["findings"].append("unpinned_repo_commit")

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
        "schema_validation_failed": sum(
            "schema_validation_failed" in item["findings"] for item in findings
        ),
        "unpinned_repo_commit": sum(
            "unpinned_repo_commit" in item["findings"] for item in findings
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
    workspace_hash = _workspace_hash(workspace)
    earned, possible, breakdown = asyncio.run(
        evaluate_partial_credit(task.verification.partial_credit, workspace)
    )
    if _workspace_hash(workspace) != workspace_hash:
        raise ValueError("Control evaluation changed its workspace")
    percent = 0 if possible == 0 else earned * 100 / possible
    return {
        "workspace": str(workspace),
        "workspace_hash": workspace_hash,
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
    if task_definition.is_symlink() or not task_definition.is_file():
        raise ValueError("Task definition must be a regular non-symlink file")
    for workspace in (gold_workspace, noop_workspace, mutation_workspace):
        _validate_control_workspace(workspace)
    controls = {
        "gold": _control_result(task_definition, gold_workspace),
        "noop": _control_result(task_definition, noop_workspace),
        "mutation": _control_result(task_definition, mutation_workspace),
    }
    complete = all(controls[name]["percent"] == score for name, score in _CONTROL_EXPECTED.items())
    evidence = {
        "status": "review_evidence_ready" if complete else "review_required",
        "admission": "not_admitted",
        "task_definition": str(task_definition),
        "task_definition_hash": task_definition_hash(task_definition),
        "protocol_version": 1,
        "evaluator": dict(_EVALUATOR),
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
    evidence["receipt_sha256"] = _receipt_hash(evidence)
    evidence["receipt"] = {
        **_RECEIPT_PROFILE,
        "sha256": evidence["receipt_sha256"],
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
    if not re.fullmatch(r"[A-Z]{2}-[0-9]{3}", task_id):
        raise ValueError("Invalid task ID in result")
    if result.get("outcome", {}).get("success") is not False:
        raise ValueError("A failure candidate needs an explicitly failed outcome")
    candidate_path = out_dir / f"{task_id}.candidate.json"
    review_path = out_dir / f"{task_id}.review.json"
    if candidate_path.exists() or review_path.exists():
        raise ValueError("Candidate or review already exists; choose a new output directory")
    candidate = {
        "status": "candidate",
        "admission": "not_admitted",
        "confirmation_eligible": False,
        "source_result": str(result_path),
        "task_id": task_id,
        "description": description,
        "oracle_review": oracle_review,
        "result": result,
    }
    review: dict[str, Any] = {
        "status": "candidate",
        "admission": "not_admitted",
        "confirmation_eligible": False,
        "description": description,
        "oracle_review": oracle_review,
        "source_result": str(result_path),
        "next_step": "Review the candidate, oracle, provenance, and controls before admission.",
    }
    if task_definition is not None:
        task_raw = _load_mapping(task_definition)
        if task_raw is None:
            raise ValueError(f"Could not read task definition from {task_definition}")
        if task_raw.get("id") != task_id:
            raise ValueError("Task definition does not match the failed task")
        review["task_definition"] = str(task_definition)
        review["task_definition_hash"] = task_definition_hash(task_definition)
        review["task_id"] = task_raw.get("id", task_id)
        review["task_repo"] = task_raw.get("repo")
        review["task_provenance"] = task_raw.get("provenance")
        candidate["task_definition_hash"] = review["task_definition_hash"]
    out_dir.mkdir(parents=True, exist_ok=True)
    with candidate_path.open("x") as handle:
        handle.write(json.dumps(candidate, indent=2) + "\n")
    with review_path.open("x") as handle:
        handle.write(json.dumps(review, indent=2) + "\n")
    return {
        "status": "candidate",
        "admission": "not_admitted",
        "candidate_path": str(candidate_path),
        "review_path": str(review_path),
    }
