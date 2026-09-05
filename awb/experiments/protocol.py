"""Pure experiment planning. Creating a plan never calls an adapter."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import defaultdict


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def create_plan(spec: dict) -> dict:
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
    if spec["safety_policy_hash_a"] != spec["safety_policy_hash_b"]:
        raise ValueError("Both arms must preserve the same safety policy")
    for field in ("repeats", "timeout_seconds"):
        if type(spec.get(field)) is not int or spec[field] <= 0:
            raise ValueError(f"{field} must be a positive integer")
    if spec["repeats"] > 100 or spec["timeout_seconds"] > 7200:
        raise ValueError("Plan exceeds bounded repeat or timeout limits")
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
    }
    return {**body, "plan_hash": fingerprint(body)}


def validate_plan(plan: dict) -> None:
    if create_plan(plan["spec"]) != plan:
        raise ValueError("Plan changed after registration or has an invalid schedule")


def assess(plan: dict, arm_a: list[dict], arm_b: list[dict], split: str) -> dict:
    """Conservative decision from corresponding, complete saved attempts."""
    from awb.scoring.statistics import compare_tools_paired

    validate_plan(plan)
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown split")
    spec = plan["spec"]
    wanted = set(spec[f"{split}_tasks"])
    reasons = []
    groups = []
    costs = []
    for arm, rows in (("a", arm_a), ("b", arm_b)):
        grouped = defaultdict(list)
        known_cost = 0.0
        cost_complete = True
        seen = set()
        for row in rows:
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
            seen.add(identity)
            if row.get("execution_status") != "completed":
                reasons.append(f"Arm {arm}/{task_id}: execution incomplete or unknown")
            outcome = row.get("outcome", {})
            maximum = outcome.get("partial_credit_max", 0)
            if maximum <= 0:
                reasons.append(f"Arm {arm}/{task_id}: no gradeable outcome")
                continue
            grouped[task_id].append(100 * outcome.get("partial_credit_score", 0) / maximum)
            cost = row.get("cost", {})
            if row.get("usage_status", cost.get("usage_status")) != "complete":
                cost_complete = False
            known_cost += cost.get("estimated_cost_usd", 0) or 0
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
