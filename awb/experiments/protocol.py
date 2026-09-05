"""Pure experiment planning. Creating a plan never calls an adapter."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
from collections import defaultdict

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
_RESERVED_ENV = {
    "AWB_BENCHMARK",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_SKIP_HOOKS",
    "HOME",
    "TMPDIR",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME",
}


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def create_plan(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("Plan specification must be a JSON object")
    spec = json.loads(json.dumps(spec))
    for field in (
        "tool",
        "model",
        "config_a_hash",
        "config_b_hash",
        "safety_policy_hash_a",
        "safety_policy_hash_b",
    ):
        if not isinstance(spec.get(field), str) or spec[field].lower() in {
            "",
            "unknown",
            "default",
        }:
            raise ValueError(f"Declare a known {field}")
    if not _MODEL_NAME.fullmatch(spec["model"]):
        raise ValueError("model must be a bounded explicit model identifier")
    if spec["safety_policy_hash_a"] != spec["safety_policy_hash_b"]:
        raise ValueError("Both arms must preserve the same safety policy")
    for field in ("repeats", "timeout_seconds"):
        if type(spec.get(field)) is not int or spec[field] <= 0:
            raise ValueError(f"{field} must be a positive integer")
    if spec["repeats"] > 100 or spec["timeout_seconds"] > 7200:
        raise ValueError("Plan exceeds bounded repeat or timeout limits")
    spec.setdefault("setup_timeout_seconds", 900)
    spec.setdefault("verification_timeout_seconds", 600)
    for field in ("setup_timeout_seconds", "verification_timeout_seconds"):
        if type(spec.get(field)) is not int or not 0 < spec[field] <= 7200:
            raise ValueError(f"{field} must be an integer between 1 and 7200")
    spec.setdefault(
        "attempt_timeout_seconds",
        spec["timeout_seconds"]
        + spec["setup_timeout_seconds"]
        + spec["verification_timeout_seconds"],
    )
    if (
        type(spec.get("attempt_timeout_seconds")) is not int
        or spec["attempt_timeout_seconds"] < spec["timeout_seconds"]
        or spec["attempt_timeout_seconds"] > 21600
    ):
        raise ValueError(
            "attempt_timeout_seconds must be an integer between timeout_seconds and 21600"
        )
    allowed_env = spec.setdefault("allowed_env", [])
    if (
        not isinstance(allowed_env, list)
        or any(not isinstance(name, str) or not _ENV_NAME.fullmatch(name) for name in allowed_env)
        or len(set(allowed_env)) != len(allowed_env)
        or any(name in _RESERVED_ENV for name in allowed_env)
    ):
        raise ValueError("allowed_env must contain unique, nonreserved environment variable names")
    if type(spec.get("seed")) is not int:
        raise ValueError("Declare an integer seed")
    threshold = spec.get("minimum_delta")
    if (
        not isinstance(threshold, int | float)
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 100
    ):
        raise ValueError("minimum_delta must be between 0 and 100")
    if spec.get("state_policy") != "fresh_process_per_attempt":
        raise ValueError("Declare fresh_process_per_attempt; persistent state is not controlled")
    development, holdout = spec.get("development_tasks"), spec.get("holdout_tasks")
    if (
        not isinstance(development, list)
        or not isinstance(holdout, list)
        or not development
        or not holdout
    ):
        raise ValueError("Declare nonempty development and holdout task lists")
    if any(not isinstance(t, str) for t in development + holdout):
        raise ValueError("Task IDs must be strings")
    if len(set(development + holdout)) != len(development + holdout):
        raise ValueError("Development and holdout tasks must be unique and disjoint")
    hashes = spec.get("task_hashes", {})
    if any(
        not isinstance(hashes.get(t), str) or len(hashes[t]) != 64 for t in development + holdout
    ):
        raise ValueError("Every task needs a SHA-256 definition hash")
    rng = random.Random(spec["seed"])
    schedule = []
    for split, task_ids in (("development", development), ("holdout", holdout)):
        task_ids = list(task_ids)
        rng.shuffle(task_ids)
        for task_id in task_ids:
            first = rng.randrange(2)
            for repeat in range(spec["repeats"]):
                arms = ["a", "b"] if (first + repeat) % 2 == 0 else ["b", "a"]
                for arm in arms:
                    schedule.append(
                        {"task_id": task_id, "repeat": repeat + 1, "arm": arm, "split": split}
                    )
    body = {
        "schema_version": 1,
        "spec": spec,
        "schedule": schedule,
        "interpretation": "Paired configuration evidence, not human productivity",
        "spend_cap": None,
        "agent_time_upper_bound_seconds": len(schedule) * spec["timeout_seconds"],
        "wall_time_upper_bound_seconds": len(schedule) * spec["attempt_timeout_seconds"],
    }
    return {**body, "plan_hash": fingerprint(body)}


def validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict) or not isinstance(plan.get("spec"), dict):
        raise ValueError("Plan must be a JSON object with a specification")
    if create_plan(plan["spec"]) != plan:
        raise ValueError("Plan changed after registration or has an invalid schedule")


def assess(
    plan: dict,
    arm_a: list[dict],
    arm_b: list[dict],
    split: str,
    *,
    execution_verified: bool = False,
) -> dict:
    """Assess corresponding saved attempts; local receipt checks are not attestation."""
    from awb.scoring.statistics import compare_tools_paired

    validate_plan(plan)
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown split")
    if not isinstance(arm_a, list) or not isinstance(arm_b, list):
        raise ValueError("Assessment arms must be JSON arrays")
    spec = plan["spec"]
    wanted = set(spec[f"{split}_tasks"])
    reasons = []
    if split == "holdout" and not execution_verified:
        reasons.append("Unverified imported evidence cannot confirm a holdout result")
    groups = []
    costs = []
    for arm, rows in (("a", arm_a), ("b", arm_b)):
        grouped = defaultdict(list)
        known_cost = 0.0
        cost_complete = True
        seen = set()
        expected = {
            (entry["task_id"], entry["repeat"])
            for entry in plan["schedule"]
            if entry["split"] == split and entry["arm"] == arm
        }
        for row in rows:
            if not isinstance(row, dict):
                reasons.append(f"Arm {arm}: attempt receipt is not an object")
                continue
            task_id = row.get("task_id")
            if task_id not in wanted:
                reasons.append(f"Arm {arm}: unexpected task {task_id}")
                continue
            if row.get("model") != spec["model"]:
                reasons.append(f"Arm {arm}/{task_id}: model differs or is unknown")
            if row.get("effective_config_hash") != spec[f"config_{arm}_hash"]:
                reasons.append(f"Arm {arm}/{task_id}: configuration differs or is unknown")
            if row.get("task_definition_hash") != spec["task_hashes"][task_id]:
                reasons.append(f"Arm {arm}/{task_id}: task definition differs or is unknown")
            if row.get("experiment_plan_hash") != plan["plan_hash"]:
                reasons.append(f"Arm {arm}/{task_id}: no matching execution plan receipt")
            identity = (task_id, row.get("repeat_index"))
            if identity in seen or type(identity[1]) is not int:
                reasons.append(f"Arm {arm}/{task_id}: duplicate or missing repeat identity")
                continue
            if identity not in expected:
                reasons.append(f"Arm {arm}/{task_id}: attempt is outside the frozen schedule")
                continue
            seen.add(identity)
            if row.get("experiment_split") != split or row.get("experiment_arm") != arm:
                reasons.append(f"Arm {arm}/{task_id}: receipt arm or split differs")
            execution = row.get("execution", {})
            if not isinstance(execution, dict):
                reasons.append(f"Arm {arm}/{task_id}: execution is not an object")
            elif execution.get("status", row.get("execution_status")) != "completed":
                reasons.append(f"Arm {arm}/{task_id}: execution incomplete or unknown")
            outcome = row.get("outcome", {})
            if not isinstance(outcome, dict):
                reasons.append(f"Arm {arm}/{task_id}: outcome is not an object")
                continue
            maximum = outcome.get("partial_credit_max")
            score = outcome.get("partial_credit_score")
            if (
                type(maximum) not in (int, float)
                or type(score) not in (int, float)
                or not math.isfinite(maximum)
                or not math.isfinite(score)
                or maximum <= 0
                or not 0 <= score <= maximum
            ):
                reasons.append(f"Arm {arm}/{task_id}: outcome is not a valid bounded score")
                continue
            grouped[task_id].append(100 * score / maximum)
            cost = row.get("cost", {})
            if not isinstance(cost, dict):
                reasons.append(f"Arm {arm}/{task_id}: cost is not an object")
                cost_complete = False
                continue
            if row.get("usage_status", cost.get("usage_status")) != "complete":
                cost_complete = False
                reasons.append(f"Arm {arm}/{task_id}: usage measurement incomplete or unknown")
            recorded_cost = cost.get("estimated_cost_usd", 0)
            if (
                type(recorded_cost) not in (int, float)
                or not math.isfinite(recorded_cost)
                or recorded_cost < 0
            ):
                cost_complete = False
                reasons.append(f"Arm {arm}/{task_id}: cost is not a valid nonnegative number")
                continue
            known_cost += recorded_cost
        if seen != expected:
            reasons.append(f"Arm {arm}: attempts do not match the frozen schedule")
        for task_id in sorted(wanted):
            if len(grouped[task_id]) != spec["repeats"]:
                reasons.append(f"Arm {arm}/{task_id}: expected {spec['repeats']} attempts")
        groups.append(grouped)
        costs.append({"recorded_usd": known_cost, "complete": cost_complete})
    shared = sorted(t for t in wanted if groups[0][t] and groups[1][t])
    a = [statistics.median(groups[0][t]) for t in shared]
    b = [statistics.median(groups[1][t]) for t in shared]
    deltas = [bv - av for av, bv in zip(a, b, strict=True)]
    mean = statistics.mean(deltas) if deltas else None
    decision = "inconclusive"
    test = compare_tools_paired(a, b) if shared else None
    p_value = test.p_value if test else None
    if len(shared) < 5:
        reasons.append("Fewer than five paired tasks; descriptive evidence only")
    if not reasons and p_value is not None and p_value < 0.05:
        if mean >= spec["minimum_delta"]:
            decision = "candidate_meets_threshold" if split == "holdout" else "confirm_on_holdout"
        elif mean <= -spec["minimum_delta"]:
            decision = "baseline_better"
    return {
        "schema_version": 1,
        "plan_hash": plan["plan_hash"],
        "split": split,
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "paired_tasks": len(shared),
        "mean_delta": mean,
        "p_value": p_value,
        "repeat_aggregation": "median",
        "per_task": [
            {
                "task_id": t,
                "a": av,
                "b": bv,
                "delta": bv - av,
                "variance_a": statistics.pvariance(groups[0][t]),
                "variance_b": statistics.pvariance(groups[1][t]),
            }
            for t, av, bv in zip(shared, a, b, strict=True)
        ],
        "cost": dict(zip(("a", "b"), costs, strict=True)),
    }
