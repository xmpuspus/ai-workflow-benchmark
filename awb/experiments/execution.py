"""Controlled execution of a frozen experiment plan.

The service accepts only local, instruction-only Claude configuration trees.
It never copies configuration files, credentials, sessions, or persistent
state. Each scheduled attempt gets a fresh runner and adapter instance.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from awb.experiments.protocol import validate_plan

_ROOT_FILES = {"settings.json", "hooks.json", "CLAUDE.md", "AGENTS.md", "AGENTS.override.md"}
_INSTRUCTION_DIRS = {"agents", "rules", "skills"}
_SAFETY_FILES = {"settings.json", "hooks.json"}
_FORBIDDEN_PARTS = {"auth.json", "credentials.json", "sessions", "state", "history.jsonl"}


def _hash_entries(entries: list[tuple[str, bytes]]) -> str:
    hasher = hashlib.sha256()
    for name, content in entries:
        hasher.update(name.encode())
        hasher.update(b"\0")
        hasher.update(content)
        hasher.update(b"\0")
    return hasher.hexdigest()


def config_snapshot(config_dir: Path) -> dict[str, Any]:
    """Hash allowed configuration files without reading credential/state files."""
    if not config_dir.is_dir():
        raise ValueError(f"Configuration directory does not exist: {config_dir}")
    entries: list[tuple[str, bytes]] = []
    safety: list[tuple[str, bytes]] = []
    for path in sorted(config_dir.rglob("*")):
        relative = path.relative_to(config_dir)
        parts = relative.parts
        if any(part.lower() in _FORBIDDEN_PARTS for part in parts):
            raise ValueError(f"Configuration file is not permitted: {relative}")
        if path.is_symlink():
            raise ValueError(f"Configuration symlink is not permitted: {relative}")
        if path.is_dir():
            continue
        allowed = len(parts) == 1 and parts[0] in _ROOT_FILES
        allowed = allowed or (len(parts) >= 2 and parts[0] in _INSTRUCTION_DIRS)
        if not allowed:
            raise ValueError(f"Configuration file is not permitted: {relative}")
        name = relative.as_posix()
        content = path.read_bytes()
        entries.append((name, content))
        if len(parts) == 1 and parts[0] in _SAFETY_FILES:
            safety.append((name, content))
    return {
        "hash": _hash_entries(entries),
        "safety_policy_hash": _hash_entries(safety),
        "files": [name for name, _ in entries],
        "instruction_files": [
            name
            for name, _ in entries
            if name in {"CLAUDE.md", "AGENTS.md", "AGENTS.override.md"}
            or name.split("/", 1)[0] in _INSTRUCTION_DIRS
        ],
    }


def _task_paths(tasks_dir: Path, wanted: set[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(tasks_dir.rglob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"Could not read task definition {path}: {exc}") from exc
        if isinstance(raw, dict) and raw.get("id") in wanted:
            task_id = raw["id"]
            if task_id in found:
                raise ValueError(f"Duplicate task definition for {task_id}")
            found[task_id] = path
    missing = wanted - found.keys()
    if missing:
        raise ValueError(f"Plan task definitions are missing: {', '.join(sorted(missing))}")
    return found


def _load_frozen_task(path: Path, task_id: str, expected_hash: str):
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"Task definition hash changed for {task_id}")
    from awb.core.task_loader import load_task

    task = load_task(path)
    if task.id != task_id:
        raise ValueError(f"Task definition identity changed for {task_id}")
    return task


def _attempt_marker(
    runs_dir: Path, plan_hash: str, split: str, task_id: str, arm: str, repeat: int
) -> Path:
    identity = hashlib.sha256(f"{split}\0{task_id}\0{arm}\0{repeat}".encode()).hexdigest()
    return runs_dir / ".experiment-attempts" / plan_hash / f"{identity}.json"


def _existing_attempts(
    runs_dir: Path, plan_hash: str, split: str
) -> dict[tuple[str, str, int], dict]:
    found: dict[tuple[str, str, int], dict] = {}
    if not runs_dir.exists():
        return found
    for path in runs_dir.rglob("*.json"):
        if ".experiment-attempts" in path.parts:
            continue
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("experiment_plan_hash") != plan_hash:
            continue
        if row.get("experiment_split") != split:
            continue
        key = (row.get("task_id"), row.get("experiment_arm"), row.get("repeat_index"))
        if not isinstance(key[0], str) or key[1] not in {"a", "b"} or not isinstance(key[2], int):
            raise ValueError(f"Invalid experiment receipt: {path}")
        if key in found:
            raise ValueError(f"Duplicate completed experiment attempt: {key}")
        if row.get("execution_status") != "completed":
            raise ValueError(f"Experiment attempt is incomplete: {key}")
        found[key] = row
    return found


class _ModelPinnedClaudeAdapter:
    """Create a fresh Claude adapter whose command always declares the plan model."""

    def __new__(cls, config_dir: Path, model: str):
        from awb.adapters.claude_code import ClaudeCodeCustomAdapter

        class ModelPinnedAdapter(ClaudeCodeCustomAdapter):
            def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
                return [*super()._get_cmd(prompt, max_turns), "--model", self.model]

        adapter = ModelPinnedAdapter(config_dir=config_dir)
        adapter.model = model
        return adapter


def _execute_attempt(
    *,
    task: Any,
    arm: str,
    repeat_index: int,
    config_dir: Path,
    model: str,
    timeout_seconds: int,
    runs_dir: Path,
    run_id: str,
    tasks_dir: Path,
) -> Path:
    """Run one task with one new runner and return its persisted result path."""
    from awb.core.results import ResultRecorder
    from awb.core.runner import BenchmarkRunner

    adapter = _ModelPinnedClaudeAdapter(config_dir, model)
    runner = BenchmarkRunner(
        tool="claude-code-custom",
        tasks=[task],
        runs=1,
        timeout_override=timeout_seconds,
        concurrency=1,
        tasks_dir=tasks_dir,
    )
    runner._adapter = adapter
    runner.recorder = ResultRecorder(results_dir=runs_dir)
    runner._run_id = run_id
    results = asyncio.run(runner.run_all())
    if len(results) != 1:
        raise RuntimeError("Experiment attempt did not produce exactly one result")
    result = results[0]
    return runs_dir / result.run_id / f"{result.task_id}_{result.tool}.json"


def _validate_inputs(
    plan: dict, config_a: Path, config_b: Path, tasks_dir: Path, split: str
) -> tuple[dict, dict, dict[str, Path]]:
    validate_plan(plan)
    if split not in {"development", "holdout"}:
        raise ValueError("split must be development or holdout")
    spec = plan["spec"]
    if spec["tool"] != "claude-code-custom":
        raise ValueError("Only claude-code-custom supports controlled execution")
    snapshot_a, snapshot_b = config_snapshot(config_a), config_snapshot(config_b)
    for arm, snapshot in (("a", snapshot_a), ("b", snapshot_b)):
        if snapshot["hash"] != spec[f"config_{arm}_hash"]:
            raise ValueError(f"config {arm.upper()} hash does not match the frozen plan")
        if snapshot["safety_policy_hash"] != spec[f"safety_policy_hash_{arm}"]:
            raise ValueError(f"config {arm.upper()} safety policy does not match the frozen plan")
    if snapshot_a["safety_policy_hash"] != snapshot_b["safety_policy_hash"]:
        raise ValueError("Both arms must preserve equal settings and hooks")
    wanted = set(spec[f"{split}_tasks"])
    return snapshot_a, snapshot_b, _task_paths(tasks_dir, wanted)


def execute_plan(
    plan: dict,
    config_a: Path,
    config_b: Path,
    tasks_dir: Path | None,
    split: str,
    runs_dir: Path,
) -> dict:
    """Execute missing frozen-plan attempts and write receipt fields to result JSON."""
    if tasks_dir is None:
        from awb.core.config import TASKS_DIR

        effective_tasks_dir = TASKS_DIR
    else:
        effective_tasks_dir = Path(tasks_dir)
    config_a, config_b, runs_dir = Path(config_a), Path(config_b), Path(runs_dir)
    snapshot_a, snapshot_b, task_paths = _validate_inputs(
        plan, config_a, config_b, effective_tasks_dir, split
    )
    spec = plan["spec"]
    existing = _existing_attempts(runs_dir, plan["plan_hash"], split)
    completed: list[dict] = []
    resumed: list[dict] = []
    executed: list[dict] = []
    schedule = [entry for entry in plan["schedule"] if entry["split"] == split]
    # Refuse before starting any new paid work if a prior process left an
    # ambiguous receipt for this plan/split. Continuing a different scheduled
    # arm would make recovery order-dependent and conceal that ambiguity.
    for entry in schedule:
        key = (entry["task_id"], entry["arm"], entry["repeat"])
        if (
            key not in existing
            and _attempt_marker(runs_dir, plan["plan_hash"], split, *key).exists()
        ):
            raise ValueError(f"Ambiguous started-but-not-finished experiment attempt: {key}")
    for entry in schedule:
        key = (entry["task_id"], entry["arm"], entry["repeat"])
        if key in existing:
            resumed.append(existing[key])
            completed.append(existing[key])
            continue
        marker = _attempt_marker(runs_dir, plan["plan_hash"], split, *key)
        # Freeze actual inputs again immediately before the paid attempt.
        snapshot_a, snapshot_b, task_paths = _validate_inputs(
            plan, config_a, config_b, effective_tasks_dir, split
        )
        arm = entry["arm"]
        config_dir = config_a if arm == "a" else config_b
        snapshot = snapshot_a if arm == "a" else snapshot_b
        task_id, repeat = entry["task_id"], entry["repeat"]
        task = _load_frozen_task(task_paths[task_id], task_id, spec["task_hashes"][task_id])
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"status": "started", "attempt": key}, indent=2) + "\n")
        run_id = f"experiment_{plan['plan_hash'][:12]}_{split}_{arm}_{repeat}_{task_id}"
        result_path = _execute_attempt(
            task=task,
            arm=arm,
            repeat_index=repeat,
            config_dir=config_dir,
            model=spec["model"],
            timeout_seconds=spec["timeout_seconds"],
            runs_dir=runs_dir,
            run_id=run_id,
            tasks_dir=effective_tasks_dir,
        )
        row = json.loads(result_path.read_text())
        row.update(
            {
                "experiment_plan_hash": plan["plan_hash"],
                "experiment_split": split,
                "experiment_arm": arm,
                "repeat_index": repeat,
                "task_definition_hash": spec["task_hashes"][task_id],
                "effective_config_hash": snapshot["hash"],
                "model": spec["model"],
                "execution_status": "completed",
                "execution_stage": "finished",
                "execution_mode": "fresh_process_per_attempt",
                "loaded_instruction_files": snapshot["instruction_files"],
            }
        )
        result_path.write_text(json.dumps(row, indent=2) + "\n")
        marker.unlink()
        executed.append(row)
        completed.append(row)
    return {
        "status": "completed",
        "plan_hash": plan["plan_hash"],
        "split": split,
        "executed_attempts": executed,
        "resumed_attempts": resumed,
        "completed_attempts": completed,
    }
