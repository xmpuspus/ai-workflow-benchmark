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
