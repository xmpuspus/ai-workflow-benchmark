"""Tests for ResultRecorder."""

import json

from awb.core.results import ResultRecorder


class TestResultRecorder:
    def test_save_creates_json_file(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        path = recorder.save(sample_result)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_file_named_by_task_and_tool(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        path = recorder.save(sample_result)
        assert sample_result.task_id in path.name
        assert sample_result.tool in path.name

    def test_save_writes_valid_json(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        path = recorder.save(sample_result)
        with open(path) as f:
            data = json.load(f)
        assert data["task_id"] == sample_result.task_id
        assert data["tool"] == sample_result.tool

    def test_load_run_returns_results(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        run_dir = tmp_workspace / sample_result.run_id
        results = recorder.load_run(run_dir)
        assert len(results) == 1
        assert results[0].task_id == sample_result.task_id

    def test_load_run_preserves_outcome(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        run_dir = tmp_workspace / sample_result.run_id
        results = recorder.load_run(run_dir)
        loaded = results[0]
        assert loaded.outcome.success == sample_result.outcome.success
        assert loaded.outcome.partial_credit_score == sample_result.outcome.partial_credit_score

    def test_load_run_preserves_metrics(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        run_dir = tmp_workspace / sample_result.run_id
        results = recorder.load_run(run_dir)
        loaded = results[0]
        assert loaded.metrics.wall_clock_seconds == sample_result.metrics.wall_clock_seconds
        assert loaded.metrics.iteration_count == sample_result.metrics.iteration_count

    def test_load_run_empty_dir(self, tmp_workspace):
        recorder = ResultRecorder(tmp_workspace)
        results = recorder.load_run(tmp_workspace)
        assert results == []

    def test_has_result_true_after_save(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        assert recorder.has_result(sample_result.run_id, sample_result.task_id, sample_result.tool)

    def test_has_result_false_before_save(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        assert not recorder.has_result(
            sample_result.run_id, sample_result.task_id, sample_result.tool
        )

    def test_load_single_returns_result(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        loaded = recorder.load_single(
            sample_result.run_id, sample_result.task_id, sample_result.tool
        )
        assert loaded is not None
        assert loaded.task_id == sample_result.task_id

    def test_load_single_returns_none_when_missing(self, tmp_workspace):
        recorder = ResultRecorder(tmp_workspace)
        result = recorder.load_single("no-run", "BF-999", "fake-tool")
        assert result is None

    def test_find_incomplete_run_returns_none_when_no_results(self, tmp_workspace):
        recorder = ResultRecorder(tmp_workspace)
        base = recorder.find_incomplete_run("fake-tool", 10)
        assert base is None

    def test_load_all_runs_empty_dir(self, tmp_workspace):
        recorder = ResultRecorder(tmp_workspace)
        runs = recorder.load_all_runs()
        assert runs == {}

    def test_load_all_runs_finds_saved_results(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        runs = recorder.load_all_runs()
        assert sample_result.run_id in runs
        assert len(runs[sample_result.run_id]) == 1
