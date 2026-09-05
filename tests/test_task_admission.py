"""Contracts for candidate task review; none of these commands admits a task."""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml
from click.testing import CliRunner

from awb.commands.task_cmd import task


def _task_definition(check: str = "test -f solved.txt") -> dict:
    return {
        "id": "BF-901",
        "category": "bug-fix",
        "title": "Require a reviewed task admission",
        "difficulty": "easy",
        "estimated_minutes": 10,
        "languages": ["python"],
        "repo": {"url": "https://example.invalid/repo", "commit": "a" * 40},
        "issue": {"description": "Create solved.txt", "files_to_examine": ["src/app.py"]},
        "verification": {
            "partial_credit": [{"criterion": "solution exists", "points": 100, "check": check}]
        },
        "constraints": {"max_iterations": 1, "timeout_seconds": 60},
        "provenance": {"source_pr_url": "https://example.invalid/pr/1", "created_at": "2026-09-05"},
    }


def _write_task(path, check: str = "test -f solved.txt"):
    path.write_text(yaml.safe_dump(_task_definition(check), sort_keys=False))
    return path


def _write_control_review(task_path, tmp_path):
    from awb.verification.task_admission import run_control_protocol

    gold, noop, mutation = tmp_path / "gold", tmp_path / "noop", tmp_path / "mutation"
    for workspace in (gold, noop, mutation):
        workspace.mkdir()
    (gold / "solved.txt").write_text("done")
    return run_control_protocol(task_path, gold, noop, mutation)


def test_audit_marks_unconditional_credit_and_missing_review_controls(tmp_path):
    _write_task(tmp_path / "BF-901.yaml", "test -f solved.txt; true")

    result = CliRunner().invoke(task, ["audit", "--tasks-dir", str(tmp_path), "--format", "json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["tasks_scanned"] == 1
    assert payload["status"] == "review_required"
    assert payload["counts"]["unconditional_credit"] == 1
    assert payload["counts"]["missing_independent_controls"] == 1
    assert payload["counts"]["reviewed"] == 0
    assert payload["findings"][0]["review_status"] == "unreviewed"


def test_controls_require_gold_100_and_noop_and_mutation_zero(tmp_path):
    task_path = _write_task(tmp_path / "BF-901.yaml")
    gold, noop, mutation = (tmp_path / "gold", tmp_path / "noop", tmp_path / "mutation")
    for workspace in (gold, noop, mutation):
        workspace.mkdir()
    (gold / "solved.txt").write_text("done")

    result = CliRunner().invoke(
        task,
        [
            "controls",
            str(task_path),
            "--gold-workspace",
            str(gold),
            "--noop-workspace",
            str(noop),
            "--mutation-workspace",
            str(mutation),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "review_evidence_ready"
    assert payload["admission"] == "not_admitted"
    assert payload["controls"]["gold"]["percent"] == 100
    assert payload["controls"]["noop"]["percent"] == 0
    assert payload["controls"]["mutation"]["percent"] == 0
    review = json.loads((tmp_path / "BF-901.review.json").read_text())
    assert review["task_definition_hash"] == hashlib.sha256(task_path.read_bytes()).hexdigest()
    assert review["admission"] == "not_admitted"


def test_controls_do_not_admit_when_mutation_receives_credit(tmp_path):
    task_path = _write_task(tmp_path / "BF-901.yaml")
    gold, noop, mutation = (tmp_path / "gold", tmp_path / "noop", tmp_path / "mutation")
    for workspace in (gold, noop, mutation):
        workspace.mkdir()
    (gold / "solved.txt").write_text("done")
    (mutation / "solved.txt").write_text("incorrectly credited")

    result = CliRunner().invoke(
        task,
        [
            "controls",
            str(task_path),
            "--gold-workspace",
            str(gold),
            "--noop-workspace",
            str(noop),
            "--mutation-workspace",
            str(mutation),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "review_required"
    assert payload["admission"] == "not_admitted"
    assert payload["controls"]["mutation"]["percent"] == 100


def test_audit_rejects_forged_percent_only_control_review(tmp_path):
    from awb.verification.task_admission import audit_tasks, task_definition_hash

    task_path = _write_task(tmp_path / "BF-901.yaml")
    (tmp_path / "BF-901.review.json").write_text(
        json.dumps(
            {
                "task_definition_hash": task_definition_hash(task_path),
                "controls": {
                    "gold": {"percent": 100},
                    "noop": {"percent": 0},
                    "mutation": {"percent": 0},
                },
            }
        )
    )

    payload = audit_tasks(tmp_path)
    assert "missing_independent_controls" in payload["findings"][0]["findings"]


def test_validate_control_review_rejects_recomputed_but_semantically_forged_receipt(tmp_path):
    from awb.verification.task_admission import (
        _receipt_hash,
        task_definition_hash,
        validate_control_review,
    )

    task_path = _write_task(tmp_path / "BF-901.yaml")
    review = {
        "status": "review_evidence_ready",
        "admission": "not_admitted",
        "protocol_version": 1,
        "evaluator": {},
        "task_definition_hash": task_definition_hash(task_path),
        "requirements": {},
        "controls": {
            name: {
                "percent": percent,
                "earned": 999,
                "possible": -1,
                "workspace_hash": "x" * 64,
                "criteria": [{}],
            }
            for name, percent in {"gold": 100, "noop": 0, "mutation": 0}.items()
        },
    }
    review["receipt_sha256"] = _receipt_hash(review)
    (tmp_path / "BF-901.review.json").write_text(json.dumps(review))
    assert validate_control_review(task_path) is False


def test_holdout_admission_requires_separate_declaration_bound_to_controls(tmp_path):
    from awb.verification.task_admission import (
        task_definition_hash,
        validate_holdout_admission,
    )

    task_path = _write_task(tmp_path / "BF-901.yaml")
    review = _write_control_review(task_path, tmp_path)
    assert validate_holdout_admission(task_path) is False

    (tmp_path / "BF-901.admission.json").write_text(
        json.dumps(
            {
                "admission": "holdout",
                "task_definition_hash": task_definition_hash(task_path),
                "control_receipt_sha256": review["receipt_sha256"],
                "reviewed_by": "independent-reviewer",
                "reviewed_at": "2026-09-05T12:30:00Z",
                "independent_oracle_review": True,
                "contamination_review": "No benchmark solution or target patch was exposed.",
            }
        )
    )

    assert validate_holdout_admission(task_path) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("admission", "development"),
        ("task_definition_hash", "0" * 64),
        ("control_receipt_sha256", "0" * 64),
        ("reviewed_by", "  "),
        ("reviewed_at", "not-a-date"),
        ("independent_oracle_review", False),
        ("contamination_review", ""),
    ],
)
def test_holdout_admission_rejects_incomplete_or_unbound_declarations(tmp_path, field, value):
    from awb.verification.task_admission import (
        task_definition_hash,
        validate_holdout_admission,
    )

    task_path = _write_task(tmp_path / "BF-901.yaml")
    review = _write_control_review(task_path, tmp_path)
    admission = {
        "admission": "holdout",
        "task_definition_hash": task_definition_hash(task_path),
        "control_receipt_sha256": review["receipt_sha256"],
        "reviewed_by": "independent-reviewer",
        "reviewed_at": "2026-09-05T12:30:00+00:00",
        "independent_oracle_review": True,
        "contamination_review": "No benchmark solution or target patch was exposed.",
    }
    admission[field] = value
    (tmp_path / "BF-901.admission.json").write_text(json.dumps(admission))

    assert validate_holdout_admission(task_path) is False


def test_controls_reject_symlinked_workspace_evidence_before_evaluation(tmp_path):
    from awb.verification.task_admission import run_control_protocol

    task_path = _write_task(tmp_path / "BF-901.yaml")
    gold, noop, mutation, outside = (
        tmp_path / "gold",
        tmp_path / "noop",
        tmp_path / "mutation",
        tmp_path / "outside",
    )
    for workspace in (gold, noop, mutation, outside):
        workspace.mkdir()
    (outside / "solved.txt").write_text("outside")
    (gold / "solved.txt").symlink_to(outside / "solved.txt")
    with pytest.raises(ValueError, match="symlink"):
        run_control_protocol(task_path, gold, noop, mutation)


def test_controls_reject_evaluator_workspace_mutation(tmp_path):
    from awb.verification.task_admission import run_control_protocol

    task_path = _write_task(tmp_path / "BF-901.yaml", "touch changed.txt; test -f solved.txt")
    gold, noop, mutation = tmp_path / "gold", tmp_path / "noop", tmp_path / "mutation"
    for workspace in (gold, noop, mutation):
        workspace.mkdir()
    (gold / "solved.txt").write_text("done")
    with pytest.raises(ValueError, match="changed its workspace"):
        run_control_protocol(task_path, gold, noop, mutation)


def test_audit_marks_schema_and_unpinned_commit_failures(tmp_path):
    invalid = _task_definition()
    invalid["estimated_minutes"] = 1
    invalid["repo"]["commit"] = "main"
    (tmp_path / "BF-901.yaml").write_text(yaml.safe_dump(invalid))

    payload = __import__("awb.verification.task_admission", fromlist=["audit_tasks"]).audit_tasks(
        tmp_path
    )
    findings = payload["findings"][0]["findings"]
    assert "schema_validation_failed" in findings
    assert "unpinned_repo_commit" in findings


def test_from_failure_requires_review_and_preserves_task_provenance(tmp_path):
    task_path = _write_task(tmp_path / "BF-901.yaml")
    result_path = tmp_path / "failure.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": "BF-901",
                "tool": "test-tool",
                "run_id": "run-1",
                "timestamp": "2026-09-05T00:00:00Z",
                "outcome": {"success": False, "partial_credit_score": 0, "partial_credit_max": 100},
            }
        )
    )
    out_dir = tmp_path / "candidates"

    result = CliRunner().invoke(
        task,
        [
            "from-failure",
            str(result_path),
            "--out",
            str(out_dir),
            "--description",
            "Agent did not create the required file.",
            "--oracle-review",
            "Confirm a file check is an independent oracle.",
            "--task-definition",
            str(task_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["admission"] == "not_admitted"
    review = json.loads((out_dir / "BF-901.review.json").read_text())
    assert review["status"] == "candidate"
    assert review["task_definition_hash"] == hashlib.sha256(task_path.read_bytes()).hexdigest()
    assert review["task_provenance"]["source_pr_url"] == "https://example.invalid/pr/1"


@pytest.mark.parametrize("task_id", ["../escape", "/tmp/escape", "bad-id"])
def test_failure_candidate_rejects_unsafe_task_id(tmp_path, task_id):
    from awb.verification.task_admission import create_failure_candidate

    source = tmp_path / "result.json"
    source.write_text(json.dumps({"task_id": task_id, "outcome": {"success": False}}))
    with pytest.raises(ValueError, match="task ID"):
        create_failure_candidate(source, tmp_path / "out", "description", "review")


def test_candidate_does_not_overwrite_prior_review(tmp_path):
    from awb.verification.task_admission import create_failure_candidate

    source = tmp_path / "result.json"
    source.write_text(json.dumps({"task_id": "BF-901", "outcome": {"success": False}}))
    out = tmp_path / "out"
    create_failure_candidate(source, out, "first", "review")
    with pytest.raises(ValueError, match="exists"):
        create_failure_candidate(source, out, "second", "review")
    assert json.loads((out / "BF-901.candidate.json").read_text())["description"] == "first"


def test_candidate_rejects_mismatched_definition(tmp_path):
    from awb.verification.task_admission import create_failure_candidate

    source = tmp_path / "result.json"
    source.write_text(json.dumps({"task_id": "BF-902", "outcome": {"success": False}}))
    definition = _write_task(tmp_path / "BF-901.yaml")
    with pytest.raises(ValueError, match="match"):
        create_failure_candidate(source, tmp_path / "out", "description", "review", definition)
