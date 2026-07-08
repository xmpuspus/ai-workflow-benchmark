"""Tests for awb/analysis/drift.py and the drift CLI command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from awb.analysis.drift import ReferenceScores, compute_drift, load_reference
from awb.commands.drift_cmd import drift


def _write_result(
    dir_path,
    task_id,
    tool="claude-code",
    score=100,
    max_score=100,
    success=None,
    cost_usd=0.5,
    task_set_hash="",
    filename=None,
):
    if success is None:
        success = score >= max_score
    data = {
        "task_id": task_id,
        "tool": tool,
        "run_id": "run1",
        "timestamp": "2026-01-01T00:00:00Z",
        "outcome": {
            "success": success,
            "partial_credit_score": score,
            "partial_credit_max": max_score,
        },
        "cost": {"estimated_cost_usd": cost_usd},
        "task_set_hash": task_set_hash,
    }
    fname = filename or f"{task_id}_{tool}_{score}.json"
    (dir_path / fname).write_text(json.dumps(data))


def _baseline_json(tool_name="claude-code", task_scores=None, task_set_hash=""):
    """task_scores: dict[task_id, list[(score, max_score)]]."""
    task_scores = task_scores or {}
    results = []
    for tid, runs in task_scores.items():
        run_entries = []
        for i, (score, max_score) in enumerate(runs, start=1):
            run_entries.append(
                {
                    "run_number": i,
                    "outcome": {
                        "success": score >= max_score,
                        "partial_credit_score": score,
                        "partial_credit_max": max_score,
                    },
                    "metrics": {"wall_clock_seconds": 10.0, "iteration_count": 1},
                    "cost": {"estimated_cost_usd": 1.0},
                    "quality": {},
                }
            )
        results.append({"task_id": tid, "runs": run_entries})
    submission = {
        "tool": {"name": tool_name, "version": "1.0"},
        "environment": {"os": "darwin", "hardware_class": "other"},
        "awb_version": "1.4.0",
    }
    if task_set_hash:
        submission["task_set_hash"] = task_set_hash
    return {"spec_version": "awb/v2", "submission": submission, "results": results}


class TestLoadReference:
    def test_run_dir_computes_per_task_mean(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result(run_dir, "BF-001", score=80)
        _write_result(run_dir, "CR-001", score=100)

        ref = load_reference(run_dir)

        assert ref.per_task == {"BF-001": 80.0, "CR-001": 100.0}
        assert ref.mean_score == 90.0
        assert ref.tool == "claude-code"

    def test_run_dir_multi_run_averaging(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result(run_dir, "BF-001", score=60, filename="BF-001_a.json")
        _write_result(run_dir, "BF-001", score=100, filename="BF-001_b.json")

        ref = load_reference(run_dir)

        assert ref.per_task["BF-001"] == 80.0

    def test_run_dir_single_task_set_hash(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result(run_dir, "BF-001", task_set_hash="abc123")
        _write_result(run_dir, "CR-001", task_set_hash="abc123")

        ref = load_reference(run_dir)

        assert ref.task_set_hash == "abc123"

    def test_run_dir_mixed_task_set_hash_is_none(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_result(run_dir, "BF-001", task_set_hash="abc123")
        _write_result(run_dir, "CR-001", task_set_hash="def456")

        ref = load_reference(run_dir)

        assert ref.task_set_hash is None

    def test_baseline_json_computes_per_task_mean(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps(
                _baseline_json(
                    task_scores={"BF-001": [(80, 100)], "CR-001": [(100, 100)]},
                )
            )
        )

        ref = load_reference(path)

        assert ref.per_task == {"BF-001": 80.0, "CR-001": 100.0}
        assert ref.mean_score == 90.0
        assert ref.tool == "claude-code"

    def test_baseline_json_multi_run_averaging(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps(_baseline_json(task_scores={"BF-001": [(60, 100), (100, 100)]})))

        ref = load_reference(path)

        assert ref.per_task["BF-001"] == 80.0

    def test_baseline_json_task_set_hash(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps(_baseline_json(task_scores={"BF-001": [(100, 100)]}, task_set_hash="hash-1"))
        )

        ref = load_reference(path)

        assert ref.task_set_hash == "hash-1"


class TestComputeDrift:
    def _refs(
        self, cur_scores, ref_scores, cur_hash=None, ref_hash=None, cur_label="cur", ref_label="ref"
    ):
        cur = ReferenceScores(
            label=cur_label,
            per_task=cur_scores,
            mean_score=sum(cur_scores.values()) / len(cur_scores),
            task_set_hash=cur_hash,
        )
        ref = ReferenceScores(
            label=ref_label,
            per_task=ref_scores,
            mean_score=sum(ref_scores.values()) / len(ref_scores),
            task_set_hash=ref_hash,
        )
        return cur, ref

    def test_threshold_boundary_exact_delta_not_drifted(self):
        cur, ref = self._refs({"BF-001": 90.0}, {"BF-001": 95.0})
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.delta == -5.0
        assert report.drifted is False

    def test_threshold_boundary_beyond_delta_drifted(self):
        cur, ref = self._refs({"BF-001": 89.9}, {"BF-001": 95.0})
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.drifted is True

    def test_no_drift_when_scores_improve(self):
        cur, ref = self._refs({"BF-001": 100.0}, {"BF-001": 80.0})
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.drifted is False
        assert report.delta == 20.0

    def test_regressions_sorted_worst_first(self):
        cur, ref = self._refs(
            {"BF-001": 90.0, "CR-001": 50.0, "DB-001": 100.0},
            {"BF-001": 100.0, "CR-001": 100.0, "DB-001": 100.0},
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert [r.task_id for r in report.regressions] == ["CR-001", "BF-001"]
        assert report.regressions[0].delta == -50.0

    def test_regressions_excludes_improved_and_unchanged_tasks(self):
        cur, ref = self._refs(
            {"BF-001": 100.0, "CR-001": 50.0},
            {"BF-001": 80.0, "CR-001": 50.0},
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert [r.task_id for r in report.regressions] == []

    def test_new_and_missing_tasks(self):
        cur, ref = self._refs(
            {"BF-001": 100.0, "NEW-001": 100.0},
            {"BF-001": 100.0, "OLD-001": 100.0},
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.new_tasks == ["NEW-001"]
        assert report.missing_tasks == ["OLD-001"]

    def test_hash_mismatch_flagged(self):
        cur, ref = self._refs(
            {"BF-001": 100.0}, {"BF-001": 100.0}, cur_hash="hash-a", ref_hash="hash-b"
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.task_set_hash_mismatch is True

    def test_hash_match_not_flagged(self):
        cur, ref = self._refs(
            {"BF-001": 100.0}, {"BF-001": 100.0}, cur_hash="hash-a", ref_hash="hash-a"
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.task_set_hash_mismatch is False

    def test_hash_mismatch_not_flagged_when_one_side_missing(self):
        cur, ref = self._refs(
            {"BF-001": 100.0}, {"BF-001": 100.0}, cur_hash=None, ref_hash="hash-b"
        )
        report = compute_drift(cur, ref, threshold=5.0)
        assert report.task_set_hash_mismatch is False


class TestDriftCommand:
    def _make_dirs(self, tmp_path, cur_scores, ref_scores):
        cur_dir = tmp_path / "current"
        cur_dir.mkdir()
        for tid, score in cur_scores.items():
            _write_result(cur_dir, tid, score=score)

        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        for tid, score in ref_scores.items():
            _write_result(ref_dir, tid, score=score)
        return cur_dir, ref_dir

    def test_exit_code_zero_when_not_drifted(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(
            tmp_path, {"BF-001": 100, "CR-001": 100}, {"BF-001": 100, "CR-001": 100}
        )
        runner = CliRunner()
        result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_exit_code_one_when_drifted(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(
            tmp_path, {"BF-001": 0, "CR-001": 0}, {"BF-001": 100, "CR-001": 100}
        )
        runner = CliRunner()
        result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir)])
        assert result.exit_code == 1
        assert "DRIFT" in result.output

    def test_json_format_honors_exit_code(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(tmp_path, {"BF-001": 0}, {"BF-001": 100})
        runner = CliRunner()
        result = runner.invoke(
            drift, [str(cur_dir), "--baseline", str(ref_dir), "--format", "json"]
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["drifted"] is True

    def test_json_format_exit_zero_when_not_drifted(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(tmp_path, {"BF-001": 100}, {"BF-001": 100})
        runner = CliRunner()
        result = runner.invoke(
            drift, [str(cur_dir), "--baseline", str(ref_dir), "--format", "json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["drifted"] is False

    def test_custom_threshold_respected(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(tmp_path, {"BF-001": 90}, {"BF-001": 100})
        runner = CliRunner()
        # delta is -10, default threshold 5.0 would drift; loosen to 20
        result = runner.invoke(
            drift, [str(cur_dir), "--baseline", str(ref_dir), "--threshold", "20"]
        )
        assert result.exit_code == 0

    def test_hash_mismatch_warning_text(self, tmp_path):
        cur_dir = tmp_path / "current"
        cur_dir.mkdir()
        _write_result(cur_dir, "BF-001", score=100, task_set_hash="hash-a")
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        _write_result(ref_dir, "BF-001", score=100, task_set_hash="hash-b")

        runner = CliRunner()
        result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir)])
        assert "hash mismatch" in result.output.lower()

    def test_baseline_as_json_file(self, tmp_path):
        cur_dir = tmp_path / "current"
        cur_dir.mkdir()
        _write_result(cur_dir, "BF-001", score=100)

        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(_baseline_json(task_scores={"BF-001": [(100, 100)]})))

        runner = CliRunner()
        result = runner.invoke(drift, [str(cur_dir), "--baseline", str(baseline_path)])
        assert result.exit_code == 0

    def test_empty_run_dir_exits_nonzero(self, tmp_path):
        cur_dir = tmp_path / "current"
        cur_dir.mkdir()
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        _write_result(ref_dir, "BF-001", score=100)

        runner = CliRunner()
        result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir)])
        assert result.exit_code == 1


class TestCliThresholdBoundary:
    """The strict `delta < -threshold` boundary, exercised at the CLI layer."""

    def _make_dirs(self, tmp_path, cur_scores, ref_scores):
        cur_dir = tmp_path / "current"
        cur_dir.mkdir()
        for tid, score in cur_scores.items():
            _write_result(cur_dir, tid, score=score)
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        for tid, score in ref_scores.items():
            _write_result(ref_dir, tid, score=score)
        return cur_dir, ref_dir

    def test_exit_zero_at_exact_threshold_text_and_json(self, tmp_path):
        # delta exactly -5.0 with default threshold 5.0: NOT drifted.
        cur_dir, ref_dir = self._make_dirs(tmp_path, {"BF-001": 95}, {"BF-001": 100})
        runner = CliRunner()
        for extra in ([], ["--format", "json"]):
            result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir), *extra])
            assert result.exit_code == 0, result.output

    def test_exit_one_just_beyond_threshold_text_and_json(self, tmp_path):
        cur_dir, ref_dir = self._make_dirs(tmp_path, {"BF-001": 94.9}, {"BF-001": 100})
        runner = CliRunner()
        for extra in ([], ["--format", "json"]):
            result = runner.invoke(drift, [str(cur_dir), "--baseline", str(ref_dir), *extra])
            assert result.exit_code == 1, result.output

    def test_empty_input_json_mode_emits_parseable_error(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        _write_result(ref_dir, "BF-001", score=100)
        runner = CliRunner()
        result = runner.invoke(drift, [str(empty), "--baseline", str(ref_dir), "--format", "json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert "error" in payload
