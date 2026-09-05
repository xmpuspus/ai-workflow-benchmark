"""Controlled execution of a frozen experiment plan.

The service accepts only local, instruction-only Claude configuration trees.
It copies vetted noncredential configuration bytes into a new temporary
directory for each try. Each scheduled try gets a fresh runner and adapter.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from awb.experiments.protocol import assess, fingerprint, validate_plan

_ROOT_FILES = {"settings.json", "hooks.json", "CLAUDE.md", "AGENTS.md", "AGENTS.override.md"}
_SAFETY_FILES = {"settings.json", "hooks.json"}
_FORBIDDEN_PARTS = {"auth.json", "credentials.json", "sessions", "state", "history.jsonl"}
_INSTRUCTION_ROOTS = {"CLAUDE.md", "AGENTS.md", "AGENTS.override.md"}
_BASE_ENV = ("PATH", "HOME", "TMPDIR")
_MAX_CONFIG_FILE_BYTES = 1024 * 1024


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
    if config_dir.is_symlink():
        raise ValueError(f"Configuration directory symlink is not permitted: {config_dir}")
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
        if not path.is_file():
            raise ValueError(f"Configuration entry is not a regular file: {relative}")
        if len(parts) != 1 or parts[0] not in _ROOT_FILES:
            raise ValueError(f"Configuration file is not permitted: {relative}")
        if path.stat().st_size > _MAX_CONFIG_FILE_BYTES:
            raise ValueError(f"Configuration file exceeds the size limit: {relative}")
        name = relative.as_posix()
        content = path.read_bytes()
        if path.suffix in {".md", ".json"}:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Configuration text file is not UTF-8: {relative}") from exc
        if path.name in _SAFETY_FILES:
            _reject_credential_environment(content, relative)
        entries.append((name, content))
        if len(parts) == 1 and parts[0] in _SAFETY_FILES:
            safety.append((name, content))
    return {
        "hash": _hash_entries(entries),
        "safety_policy_hash": _hash_entries(safety),
        "files": [name for name, _ in entries],
        "entries": entries,
        "instruction_files": [name for name, _ in entries if name in _INSTRUCTION_ROOTS],
    }


def _reject_credential_environment(content: bytes, relative: Path) -> None:
    """Reject credential-like environment keys without exposing their values."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Configuration JSON is invalid: {relative}") from exc

    def visit(value: Any, parent: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if parent.lower() == "env" and any(
                    word in key.lower()
                    for word in ("key", "token", "secret", "password", "credential", "auth")
                ):
                    raise ValueError(f"Credential environment key is not permitted in {relative}")
                visit(nested, key)
        elif isinstance(value, list):
            for nested in value:
                visit(nested, parent)

    visit(data)


@contextlib.contextmanager
def _isolated_config(snapshot: dict[str, Any], parent: Path):
    """Materialize only reviewed config bytes into a fresh temporary directory."""
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="attempt-", dir=parent) as directory:
        destination = Path(directory)
        for relative, content in snapshot["entries"]:
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        yield destination


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


def _existing_attempts(runs_dir: Path, plan: dict, split: str) -> dict[tuple[str, str, int], dict]:
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
        if not isinstance(row, dict) or row.get("experiment_plan_hash") != plan["plan_hash"]:
            continue
        if row.get("experiment_split") != split:
            continue
        key = (row.get("task_id"), row.get("experiment_arm"), row.get("repeat_index"))
        if not isinstance(key[0], str) or key[1] not in {"a", "b"} or not isinstance(key[2], int):
            raise ValueError(f"Invalid experiment receipt: {path}")
        if key in found:
            raise ValueError(f"Duplicate completed experiment attempt: {key}")
        spec = plan["spec"]
        if key[0] not in spec[f"{split}_tasks"] or not 1 <= key[2] <= spec["repeats"]:
            raise ValueError(f"Experiment receipt is outside the frozen schedule: {key}")
        if row.get("task_definition_hash") != spec["task_hashes"][key[0]]:
            raise ValueError(f"Experiment receipt task hash differs: {key}")
        if row.get("effective_config_hash") != spec[f"config_{key[1]}_hash"]:
            raise ValueError(f"Experiment receipt config hash differs: {key}")
        if row.get("model") != spec["model"]:
            raise ValueError(f"Experiment receipt model differs or is unknown: {key}")
        if row.get("execution", {}).get("status", row.get("execution_status")) != "completed":
            raise ValueError(f"Experiment attempt is incomplete: {key}")
        found[key] = row
    return found


class _ModelPinnedClaudeAdapter:
    """Create a fresh Claude adapter whose command always declares the plan model."""

    def __new__(cls, config_dir: Path, model: str, allowed_env: tuple[str, ...] = ()):
        from awb.adapters.claude_code import ClaudeCodeCustomAdapter

        class ModelPinnedAdapter(ClaudeCodeCustomAdapter):
            def _get_env(self) -> dict[str, str]:
                environment = {
                    name: os.environ[name]
                    for name in (*_BASE_ENV, *allowed_env)
                    if name in os.environ
                }
                environment["AWB_BENCHMARK"] = "1"
                environment["CLAUDE_CONFIG_DIR"] = str(self.config_dir)
                return environment

            def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
                command = super()._get_cmd(prompt, max_turns)
                command = [part for part in command if part != "--dangerously-skip-permissions"]
                return [*command, "--model", self.model]

            async def execute(self, *args, **kwargs):
                result = await super().execute(*args, **kwargs)
                if not result.model:
                    result.model = "unknown"
                return result

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
    setup_timeout_seconds: int,
    verification_timeout_seconds: int,
    attempt_timeout_seconds: int,
    allowed_env: tuple[str, ...],
    runs_dir: Path,
    run_id: str,
    tasks_dir: Path,
) -> Path:
    """Run one task with one new runner and return its persisted result path."""
    from awb.core.results import ResultRecorder
    from awb.core.runner import BenchmarkRunner

    adapter = _ModelPinnedClaudeAdapter(config_dir, model, allowed_env)
    runner = BenchmarkRunner(
        tool="claude-code-custom",
        tasks=[task],
        runs=1,
        timeout_override=timeout_seconds,
        setup_timeout_seconds=setup_timeout_seconds,
        verification_timeout_seconds=verification_timeout_seconds,
        experiment_timeout_seconds=attempt_timeout_seconds,
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


def _preflight_runtime(
    snapshots: tuple[dict[str, Any], dict[str, Any]],
    model: str,
    allowed_env: tuple[str, ...],
    runs_dir: Path,
) -> None:
    missing = [name for name in allowed_env if name not in os.environ]
    if missing:
        raise ValueError(f"Allowed environment variable is not set: {', '.join(missing)}")
    for snapshot in snapshots:
        with _isolated_config(snapshot, runs_dir / ".experiment-preflight") as config_dir:
            adapter = _ModelPinnedClaudeAdapter(config_dir, model, allowed_env)
            environment = adapter._get_env()
            if shutil.which("claude", path=environment.get("PATH", "")) is None:
                raise ValueError("claude command is not available in the allowed PATH")
            command = adapter._get_cmd("preflight", 1)
            if command[-2:] != ["--model", model] or "--dangerously-skip-permissions" in command:
                raise ValueError("Could not pin the declared model and safety boundary")


def _validate_holdout_controls(paths: dict[str, Path]) -> None:
    from awb.verification.task_admission import validate_control_review

    invalid = [task_id for task_id, path in paths.items() if not validate_control_review(path)]
    if invalid:
        raise ValueError(
            "Holdout tasks lack reviewed positive and negative control evidence: "
            + ", ".join(sorted(invalid))
        )


def _validate_inputs(
    plan: dict, config_a: Path, config_b: Path, tasks_dir: Path, split: str
) -> tuple[dict, dict, dict[str, Any]]:
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
    paths = _task_paths(tasks_dir, wanted)
    if split == "holdout":
        _validate_holdout_controls(paths)
    tasks = {
        task_id: _load_frozen_task(paths[task_id], task_id, spec["task_hashes"][task_id])
        for task_id in wanted
    }
    return snapshot_a, snapshot_b, tasks


@contextlib.contextmanager
def _plan_lock(runs_dir: Path, plan_hash: str):
    """Serialize one plan so concurrent invocations cannot spend the same arm twice."""
    locks = runs_dir / ".experiment-locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / f"{plan_hash}.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _create_marker(path: Path, attempt: tuple[str, str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as handle:
            json.dump({"status": "started", "attempt": attempt}, handle)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(
            f"Ambiguous started-but-not-finished experiment attempt: {attempt}"
        ) from exc


def _require_development_confirmation(runs_dir: Path, plan: dict) -> None:
    existing = _existing_attempts(runs_dir, plan, "development")
    expected = [entry for entry in plan["schedule"] if entry["split"] == "development"]
    if len(existing) != len(expected):
        raise ValueError("Holdout execution needs all matching development attempts")
    arms = {arm: [row for key, row in existing.items() if key[1] == arm] for arm in ("a", "b")}
    decision = assess(plan, arms["a"], arms["b"], "development")
    if decision["decision"] != "confirm_on_holdout":
        raise ValueError("Holdout execution needs an eligible development confirmation decision")


def _holdout_identity(plan: dict) -> str:
    spec = plan["spec"]
    return fingerprint(
        {
            "holdout_task_hashes": {
                task_id: spec["task_hashes"][task_id] for task_id in sorted(spec["holdout_tasks"])
            },
            "candidate_config_hash": spec["config_b_hash"],
            "model": spec["model"],
            "safety_policy_hash": spec["safety_policy_hash_b"],
        }
    )


def _claim_holdout(runs_dir: Path, plan: dict) -> Path:
    claim = runs_dir / ".experiment-holdouts" / f"{_holdout_identity(plan)}.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    payload = {"plan_hash": plan["plan_hash"], "holdout_identity": _holdout_identity(plan)}
    try:
        with claim.open("x") as handle:
            json.dump(payload, handle)
            handle.write("\n")
    except FileExistsError:
        try:
            existing = json.loads(claim.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Holdout consumption record is invalid") from exc
        if existing != payload:
            raise ValueError(
                "This holdout cohort was already consumed by a different plan"
            ) from None
    return claim


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
    snapshot_a, snapshot_b, tasks = _validate_inputs(
        plan, config_a, config_b, effective_tasks_dir, split
    )
    spec = plan["spec"]
    allowed_env = tuple(spec["allowed_env"])
    _preflight_runtime((snapshot_a, snapshot_b), spec["model"], allowed_env, runs_dir)
    completed: list[dict] = []
    resumed: list[dict] = []
    executed: list[dict] = []
    schedule = [entry for entry in plan["schedule"] if entry["split"] == split]
    with _plan_lock(runs_dir, plan["plan_hash"]):
        if split == "holdout":
            _require_development_confirmation(runs_dir, plan)
            _claim_holdout(runs_dir, plan)
        existing = _existing_attempts(runs_dir, plan, split)
        # Refuse before starting any new paid work if a prior process left an
        # ambiguous receipt for this plan/split. Continuing a different arm
        # would conceal that uncertainty.
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
            # Re-freeze all selected task hashes and both config trees before
            # each paid try, so a later file edit cannot alter the cohort.
            snapshot_a, snapshot_b, tasks = _validate_inputs(
                plan, config_a, config_b, effective_tasks_dir, split
            )
            arm = entry["arm"]
            snapshot = snapshot_a if arm == "a" else snapshot_b
            task_id, repeat = entry["task_id"], entry["repeat"]
            run_id = f"experiment_{plan['plan_hash'][:12]}_{split}_{arm}_{repeat}_{task_id}"
            with _isolated_config(snapshot, runs_dir / ".experiment-configs") as isolated_config:
                marker = _attempt_marker(runs_dir, plan["plan_hash"], split, *key)
                _create_marker(marker, key)
                result_path = _execute_attempt(
                    task=tasks[task_id],
                    arm=arm,
                    repeat_index=repeat,
                    config_dir=isolated_config,
                    model=spec["model"],
                    timeout_seconds=spec["timeout_seconds"],
                    setup_timeout_seconds=spec["setup_timeout_seconds"],
                    verification_timeout_seconds=spec["verification_timeout_seconds"],
                    attempt_timeout_seconds=spec["attempt_timeout_seconds"],
                    allowed_env=allowed_env,
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
                    "requested_model": spec["model"],
                    "experiment_attempt_status": "attempted",
                    "experiment_state_policy": "fresh_process_per_attempt",
                    "configured_instruction_files": snapshot["instruction_files"],
                }
            )
            result_path.write_text(json.dumps(row, indent=2) + "\n")
            marker.unlink()
            executed.append(row)
            completed.append(row)
            if (
                row.get("execution", {}).get("status", row.get("execution_status")) != "completed"
                or row.get("model") != spec["model"]
            ):
                break
    eligible = all(
        row.get("execution", {}).get("status", row.get("execution_status")) == "completed"
        and row.get("model") == spec["model"]
        for row in completed
    )
    return {
        "status": "completed" if eligible else "review_required",
        "plan_hash": plan["plan_hash"],
        "split": split,
        "executed_attempts": executed,
        "resumed_attempts": resumed,
        "completed_attempts": completed,
    }
