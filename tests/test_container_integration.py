"""Opt-in full pipeline check with deterministic positive and negative controls."""

import json
import os
import subprocess
from pathlib import Path

import pytest


def test_setup_agent_and_oracle_execute_inside_container(tmp_path):
    image = os.environ.get("AWB_TEST_CONTAINER_IMAGE")
    if not image:
        pytest.skip("Set AWB_TEST_CONTAINER_IMAGE to a Python image with git and AWB dependencies")
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "AWB_SMOKE_HOST_SECRET": "must-not-reach-container"}
    process = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--init",
            "--network=none",
            "--cpus=2",
            "--memory=1g",
            "--pids-limit=128",
            "--mount",
            f"type=bind,src={root},dst=/opt/awb,readonly",
            "--mount",
            f"type=bind,src={tmp_path},dst=/results",
            "--env=PYTHONPATH=/opt/awb",
            image,
            "python3",
            "/opt/awb/tests/container_smoke.py",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    rows = json.loads((tmp_path / "container-controls.json").read_text())
    assert [row["score"] for row in rows] == [100, 0]
    assert [row["success"] for row in rows] == [True, False]
    for control in ("gold", "noop"):
        result = json.loads((tmp_path / control / "BF-901_control.json").read_text())
        assert result["execution"]["status"] == "completed"
        assert result["execution_mode"] == "container"
