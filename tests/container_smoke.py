"""Run real setup, adapter subprocesses, verification and persistence in Docker.

The deterministic control adapter is a test fixture, not a model benchmark.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult
from awb.adapters.registry import _cache
from awb.core.config import (
    PartialCreditCriterion,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)
from awb.core.results import ResultRecorder
from awb.core.runner import BenchmarkRunner
from awb.core.subprocesses import run_exec


class ControlAdapter(ToolAdapter):
    name = "control"
    display_name = "Deterministic verification control"
    solve = True

    def check_available(self):
        return True

    def get_config_hash(self):
        return "gold" if self.solve else "noop"

    def get_version(self):
        return "control-v1"

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=60, on_event=None):
        assert (workspace / "setup-marker").read_text() == "container"
        assert "AWB_SMOKE_HOST_SECRET" not in os.environ
        script = (
            "from pathlib import Path; "
            "Path('solution.py').write_text('def add(a,b): return a+b\\n')"
        )
        result = await run_exec(
            "python3",
            "-c",
            script if self.solve else "pass",
            cwd=workspace,
            timeout=timeout_seconds,
        )
        return ToolResult(
            success=result.exit_code == 0, exit_code=result.exit_code, model="deterministic-control"
        )


async def main():
    repo = Path("/tmp/control-source")
    repo.mkdir()
    (repo / "solution.py").write_text("def add(a,b): return a-b\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "solution.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Xavier Puspus",
            "-c",
            "user.email=36430014+xmpuspus@users.noreply.github.com",
            "commit",
            "-m",
            "Create deterministic container control",
        ],
        check=True,
        capture_output=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    oracle = "python3 /opt/awb/tests/container_oracle.py"
    task = TaskDefinition(
        id="BF-901",
        category="bug-fix",
        title="Repair the arithmetic control fixture",
        difficulty="easy",
        estimated_minutes=5,
        languages=["python"],
        constraints=TaskConstraints(timeout_seconds=60),
        repo=TaskRepo(
            url=repo.as_uri(), commit=commit, setup_commands=["printf container > setup-marker"]
        ),
        verification=TaskVerification(
            test_commands=[oracle],
            partial_credit=[
                PartialCreditCriterion(criterion="Addition works", points=100, check=oracle)
            ],
        ),
    )
    _cache["control"] = ControlAdapter
    rows = []
    for name, solve in (("gold", True), ("noop", False)):
        runner = BenchmarkRunner(
            "control",
            [task],
            runs=1,
            concurrency=1,
            execution_mode="container",
            container_image="awb-evidence-controls",
        )
        runner._adapter.solve = solve
        runner.recorder = ResultRecorder(Path("/results"))
        row = await runner.run_single(task, run_id=name)
        assert row.outcome.partial_credit_score == (100 if solve else 0)
        assert row.outcome.success is solve
        assert row.execution.status == "completed"
        rows.append(
            {
                "control": name,
                "score": row.outcome.partial_credit_score,
                "success": row.outcome.success,
                "execution": row.execution.status,
            }
        )
    Path("/results/container-controls.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows))


if __name__ == "__main__":
    asyncio.run(main())
