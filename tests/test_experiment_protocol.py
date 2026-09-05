import copy

import pytest


def spec():
    return {
        "tool": "claude-code-custom",
        "model": "fixed-model",
        "config_a_hash": "a" * 64,
        "config_b_hash": "b" * 64,
        "safety_policy_hash_a": "s" * 64,
        "safety_policy_hash_b": "s" * 64,
        "task_hashes": {"BF-001": "1" * 64, "BF-002": "2" * 64},
        "development_tasks": ["BF-001"],
        "holdout_tasks": ["BF-002"],
        "repeats": 2,
        "seed": 42,
        "timeout_seconds": 300,
        "minimum_delta": 5.0,
        "state_policy": "fresh_process_per_attempt",
        "allowed_env": [],
    }


def test_protocol_is_deterministic_and_counterbalanced():
    from awb.experiments.protocol import create_plan

    plan = create_plan(spec())
    assert plan == create_plan(spec())
    schedule = plan["schedule"]
    assert len(schedule) == 8
    assert [s["arm"] for s in schedule[:4]] in (["a", "b", "b", "a"], ["b", "a", "a", "b"])
    assert {s["split"] for s in schedule[:4]} == {"development"}
    assert {s["split"] for s in schedule[4:]} == {"holdout"}


@pytest.mark.parametrize(
    "change",
    [
        {"holdout_tasks": ["BF-001"]},
        {"safety_policy_hash_b": "different"},
        {"repeats": 0},
        {"model": "unknown"},
        {"model": "-unsafe-option"},
        {"timeout_seconds": 0},
    ],
)
def test_protocol_rejects_uncontrolled_comparisons(change):
    from awb.experiments.protocol import create_plan

    data = spec()
    data.update(change)
    with pytest.raises(ValueError):
        create_plan(data)


@pytest.mark.parametrize("allowed_env", [["TOKEN", "TOKEN"], ["BAD-NAME"], "TOKEN"])
def test_protocol_rejects_invalid_environment_allowlist(allowed_env):
    from awb.experiments.protocol import create_plan

    data = spec()
    data["allowed_env"] = allowed_env
    with pytest.raises(ValueError, match="allowed_env"):
        create_plan(data)


def test_protocol_freezes_stage_and_attempt_deadlines():
    from awb.experiments.protocol import create_plan

    plan = create_plan(spec())
    assert plan["spec"]["setup_timeout_seconds"] > 0
    assert plan["spec"]["verification_timeout_seconds"] > 0
    assert plan["spec"]["attempt_timeout_seconds"] >= plan["spec"]["timeout_seconds"]


def test_protocol_hash_detects_post_registration_edits():
    from awb.experiments.protocol import create_plan, validate_plan

    plan = create_plan(spec())
    validate_plan(plan)
    changed = copy.deepcopy(plan)
    changed["spec"]["minimum_delta"] = 0
    with pytest.raises(ValueError, match="changed"):
        validate_plan(changed)


def test_evidence_bundle_detects_tampering_and_excludes_ambient_files(tmp_path):
    from awb.experiments.evidence import build_bundle, verify_bundle

    run = tmp_path / "run"
    run.mkdir()
    (run / "BF-001.json").write_text('{"task_id":"BF-001","outcome":{"success":true}}')
    (run / "auth.json").write_text('{"secret":"not-for-export"}')
    bundle = tmp_path / "bundle"
    build_bundle(run, bundle)
    assert verify_bundle(bundle) == []
    assert not (bundle / "auth.json").exists()
    (bundle / "BF-001.json").write_text("{}")
    assert "BF-001.json" in " ".join(verify_bundle(bundle))


def test_bundle_rejects_result_symlinks(tmp_path):
    from awb.experiments.evidence import build_bundle

    run = tmp_path / "run"
    run.mkdir()
    secret = tmp_path / "private.json"
    secret.write_text('{"task_id":"BF-001"}')
    (run / "BF-001.json").symlink_to(secret)
    with pytest.raises(ValueError, match="symlink"):
        build_bundle(run, tmp_path / "bundle")


def test_bundle_preserves_nested_experiment_receipts_and_declared_attachments(tmp_path):
    from awb.experiments.evidence import build_bundle, verify_bundle

    run = tmp_path / "runs"
    nested = run / "experiment_run1"
    nested.mkdir(parents=True)
    result = nested / "BF-001_claude-code-custom.json"
    result.write_text('{"task_id":"BF-001","outcome":{"success":true}}')
    (run / "plan.json").write_text('{"plan_hash":"abc","spec":{}}')
    (run / "evaluator.json").write_text('{"version":"1"}')
    (run / "environment.json").write_text('{"fingerprint":"env"}')
    trace = nested / "BF-001_claude-code-custom.trace.jsonl"
    trace.write_text('{"span_name":"tool"}\n')
    (run / "auth.json").write_text('{"secret":"never-export"}')

    bundle = tmp_path / "bundle"
    manifest = build_bundle(run, bundle, attachments=[trace])

    assert "experiment_run1/BF-001_claude-code-custom.json" in manifest["files"]
    assert "attachments/experiment_run1/BF-001_claude-code-custom.trace.jsonl" in manifest["files"]
    assert manifest["metadata"]["complete"] is True
    assert manifest["privacy"]["attachments"] == "explicitly selected; review before sharing"
    assert not (bundle / "auth.json").exists()
    assert verify_bundle(bundle) == []
    (bundle / "experiment_run1" / "BF-001_claude-code-custom.json").write_text("{}")
    assert "checksum" in " ".join(verify_bundle(bundle)).lower()


def test_bundle_rejects_attachment_through_symlinked_ancestor(tmp_path):
    from awb.experiments.evidence import build_bundle

    run = tmp_path / "run"
    run.mkdir()
    (run / "BF-001.json").write_text('{"task_id":"BF-001"}')
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.patch").write_text("outside")
    (run / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink|inside"):
        build_bundle(
            run,
            tmp_path / "bundle",
            attachments=[run / "linked" / "secret.patch"],
        )


def test_bundle_verifier_rejects_nonobject_manifest(tmp_path):
    from awb.experiments.evidence import verify_bundle

    (tmp_path / "manifest.json").write_text("[]")
    with pytest.raises(ValueError, match="manifest"):
        verify_bundle(tmp_path)


def test_bundle_verifier_rejects_no_results_and_false_complete_metadata(tmp_path):
    import hashlib
    import json

    from awb.experiments.evidence import verify_bundle

    payload = b"not a result"
    (tmp_path / "only.patch").write_bytes(payload)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "metadata": {"complete": True, "artifacts": {}},
                "files": {"only.patch": hashlib.sha256(payload).hexdigest()},
            }
        )
    )
    errors = verify_bundle(tmp_path)
    assert any("result" in error.lower() for error in errors)
    assert any("metadata" in error.lower() for error in errors)


def test_assessment_incomplete_or_wrong_model_is_inconclusive():
    from awb.experiments.protocol import assess, create_plan

    plan = create_plan(spec())
    assert assess(plan, [], [], "development")["decision"] == "inconclusive"
    row = {"task_id": "BF-001", "model": "different", "outcome": {"success": True}}
    result = assess(plan, [row], [row], "development")
    assert result["decision"] == "inconclusive"
    assert any("model" in reason for reason in result["reasons"])


def test_assessment_rejects_repeats_outside_frozen_schedule():
    from awb.experiments.protocol import assess, create_plan

    data = spec()
    data["development_tasks"] = [f"BF-{number:03}" for number in range(1, 7)]
    data["holdout_tasks"] = [f"BF-{number:03}" for number in range(7, 13)]
    data["task_hashes"] = {
        task_id: f"{index % 10}" * 64
        for index, task_id in enumerate(data["development_tasks"] + data["holdout_tasks"])
    }
    plan = create_plan(data)

    def rows(arm):
        return [
            {
                "task_id": task_id,
                "model": data["model"],
                "effective_config_hash": data[f"config_{arm}_hash"],
                "task_definition_hash": data["task_hashes"][task_id],
                "experiment_plan_hash": plan["plan_hash"],
                "experiment_split": "development",
                "experiment_arm": arm,
                "repeat_index": repeat,
                "execution_status": "completed",
                "usage_status": "complete",
                "outcome": {
                    "partial_credit_score": 0 if arm == "a" else 100,
                    "partial_credit_max": 100,
                },
            }
            for task_id in data["development_tasks"]
            for repeat in (98, 99)
        ]

    result = assess(plan, rows("a"), rows("b"), "development")
    assert result["decision"] == "inconclusive"
    assert any("schedule" in reason for reason in result["reasons"])


def test_assessment_cannot_win_with_incomplete_usage():
    from awb.experiments.protocol import assess, create_plan

    data = spec()
    data["development_tasks"] = [f"BF-{number:03}" for number in range(1, 7)]
    data["holdout_tasks"] = [f"BF-{number:03}" for number in range(7, 13)]
    data["repeats"] = 1
    data["task_hashes"] = {
        task_id: f"{index % 10}" * 64
        for index, task_id in enumerate(data["development_tasks"] + data["holdout_tasks"])
    }
    plan = create_plan(data)

    def rows(arm):
        return [
            {
                "task_id": task_id,
                "model": data["model"],
                "effective_config_hash": data[f"config_{arm}_hash"],
                "task_definition_hash": data["task_hashes"][task_id],
                "experiment_plan_hash": plan["plan_hash"],
                "experiment_split": "development",
                "experiment_arm": arm,
                "repeat_index": 1,
                "execution_status": "completed",
                "usage_status": "unknown" if arm == "b" else "complete",
                "outcome": {
                    "partial_credit_score": 0 if arm == "a" else 100,
                    "partial_credit_max": 100,
                },
            }
            for task_id in data["development_tasks"]
        ]

    result = assess(plan, rows("a"), rows("b"), "development")
    assert result["decision"] == "inconclusive"
    assert any("usage" in reason for reason in result["reasons"])


def test_experiment_cli_json_error_and_plan(tmp_path):
    import json

    from click.testing import CliRunner

    from awb.commands.experiment_cmd import experiment

    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec()))
    output = tmp_path / "plan.json"
    result = CliRunner().invoke(experiment, ["plan", str(path), "--out", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["plan_hash"]
    result = CliRunner().invoke(experiment, ["verify-bundle", str(tmp_path)])
    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "error"


def test_snapshot_command_does_not_expose_configuration_content(tmp_path):
    import json

    from click.testing import CliRunner

    from awb.commands.experiment_cmd import experiment

    config = tmp_path / "config"
    config.mkdir()
    (config / "CLAUDE.md").write_text("private instruction text")
    result = CliRunner().invoke(experiment, ["snapshot", str(config)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["hash"]) == 64
    assert "private instruction text" not in result.output
    assert "entries" not in payload


def test_run_command_rejects_invalid_plan_before_adapter(tmp_path):
    import json

    from click.testing import CliRunner

    from awb.commands.experiment_cmd import experiment

    path = tmp_path / "plan.json"
    path.write_text("{}")
    result = CliRunner().invoke(
        experiment,
        [
            "run",
            str(path),
            "--config-a",
            str(tmp_path),
            "--config-b",
            str(tmp_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.output)["status"] == "error"
    assert not (tmp_path / "runs").exists()
