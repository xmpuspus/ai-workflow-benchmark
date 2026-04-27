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


class TestJSONLResults:
    def test_save_creates_jsonl(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        jsonl_files = list(tmp_workspace.glob("*.jsonl"))
        assert len(jsonl_files) >= 1

    def test_load_jsonl_roundtrips(self, tmp_workspace, sample_result):
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        # Extract base ID from run_id
        import re

        match = re.match(r"^(.+)_run\d+$", sample_result.run_id)
        base_id = match.group(1) if match else sample_result.run_id
        loaded = recorder.load_jsonl(base_id)
        assert len(loaded) == 1
        assert loaded[0].task_id == sample_result.task_id

    def test_load_jsonl_missing_file(self, tmp_workspace):
        recorder = ResultRecorder(tmp_workspace)
        loaded = recorder.load_jsonl("nonexistent")
        assert loaded == []

    def test_jsonl_includes_new_cost_fields(self, tmp_workspace, sample_result):
        sample_result.cost.cache_read_tokens = 5000
        sample_result.cost.cache_creation_tokens = 1000
        sample_result.cost.thinking_tokens = 200
        recorder = ResultRecorder(tmp_workspace)
        recorder.save(sample_result)
        import re

        match = re.match(r"^(.+)_run\d+$", sample_result.run_id)
        base_id = match.group(1) if match else sample_result.run_id
        loaded = recorder.load_jsonl(base_id)
        assert loaded[0].cost.cache_read_tokens == 5000
        assert loaded[0].cost.cache_creation_tokens == 1000
        assert loaded[0].cost.thinking_tokens == 200


class TestSchemaV2:
    def test_save_emits_schema_version_2(self, tmp_workspace, sample_result):
        sample_result.task_set_hash = "deadbeef" * 8
        recorder = ResultRecorder(tmp_workspace)
        path = recorder.save(sample_result)
        with open(path) as f:
            data = json.load(f)
        assert data["schema_version"] == 2
        assert data["task_set_hash"] == "deadbeef" * 8

    def test_v2_result_validates_against_bundled_schema(self, tmp_workspace, sample_result):
        import jsonschema

        from awb.core.config import PKG_RESULT_SCHEMA_PATH

        sample_result.task_set_hash = "ab" * 32  # 64 hex chars
        recorder = ResultRecorder(tmp_workspace)
        path = recorder.save(sample_result)
        with open(path) as f:
            data = json.load(f)
        with open(PKG_RESULT_SCHEMA_PATH) as f:
            schema = json.load(f)
        # Strip legacy 'version' key — v2 schema is strict (additionalProperties: false)
        data.pop("version", None)
        jsonschema.validate(instance=data, schema=schema)

    def test_v2_schema_rejects_unknown_top_level_field(self):
        import jsonschema
        import pytest as _pytest

        from awb.core.config import PKG_RESULT_SCHEMA_PATH

        with open(PKG_RESULT_SCHEMA_PATH) as f:
            schema = json.load(f)
        bogus = {
            "schema_version": 2,
            "task_id": "BF-001",
            "tool": "x",
            "run_id": "r",
            "timestamp": "2026-04-27T00:00:00Z",
            "task_set_hash": "0" * 64,
            "outcome": {"success": True, "partial_credit_score": 0, "partial_credit_max": 0},
            "metrics": {},
            "cost": {},
            "quality": {},
            "environment": {},
            "extra_field": "should-not-validate",
        }
        with _pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bogus, schema=schema)


class TestMigrateV1ToV2:
    def test_v1_data_gets_schema_version_and_task_set_hash(self):
        from awb.commands.migrate import _migrate_one

        v1 = {"version": "1.0", "task_id": "BF-001", "tool": "x"}
        v2 = _migrate_one(v1)
        assert v2["schema_version"] == 2
        assert "task_set_hash" in v2
        assert v2["trace_path"] == ""

    def test_v2_data_is_idempotent(self):
        from awb.commands.migrate import _migrate_one

        already = {"schema_version": 2, "task_id": "BF-001", "task_set_hash": "ab" * 32}
        out = _migrate_one(already)
        assert out is already

    def test_v05x_data_passes_through_v1_then_v2(self):
        from awb.commands.migrate import _migrate_one

        v05 = {"task_id": "BF-001", "tool": "x"}  # no version key
        v2 = _migrate_one(v05)
        assert v2["schema_version"] == 2
        assert v2["version"] == "1.0"
        assert "_v05x_original" in v2
