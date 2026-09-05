"""Comparison cohort identity and conservative eligibility checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass


def _known(value: object) -> bool:
    return value is not None and value != "" and value != "unknown"


def _first_known(*values: object) -> str:
    return str(next((value for value in values if _known(value)), ""))


def _selection_identity(manifest: dict) -> str:
    explicit = manifest.get("selection_identity") or manifest.get("task_selection_hash")
    if _known(explicit):
        return str(explicit)
    task_ids = manifest.get("selected_task_ids")
    repeats = manifest.get("requested_repeats")
    if not isinstance(task_ids, list) or not task_ids or type(repeats) is not int or repeats <= 0:
        return ""
    payload = {"selected_task_ids": sorted(task_ids), "requested_repeats": repeats}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class CohortIdentity:
    task_set_hash: str = ""
    selection_identity: str = ""
    model: str = ""
    adapter_version: str = ""
    config_hash: str = ""
    evaluator_version: str = ""
    execution_mode: str = ""
    environment_fingerprint: str = ""
    budget_fingerprint: str = ""

    @property
    def missing_fields(self) -> list[str]:
        return [name for name, value in asdict(self).items() if not _known(value)]

    @property
    def eligible(self) -> bool:
        return not self.missing_fields

    @property
    def cohort_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def identity_from_result(result) -> CohortIdentity:
    workflow = getattr(result, "workflow", None)
    environment = result.environment
    environment_fingerprint = getattr(result, "environment_fingerprint", "")
    cohort_manifest = getattr(result, "cohort_manifest", {}) or {}
    if not _known(environment_fingerprint) and _known(getattr(environment, "pip_freeze_hash", "")):
        environment_fingerprint = "|".join(
            [
                environment.os,
                environment.hardware,
                environment.python_version,
                environment.pip_freeze_hash,
            ]
        )
    return CohortIdentity(
        task_set_hash=_first_known(
            getattr(result, "task_set_hash", ""), cohort_manifest.get("task_set_hash", "")
        ),
        selection_identity=_selection_identity(cohort_manifest),
        model=_first_known(getattr(result, "model", ""), getattr(workflow, "model", "")),
        adapter_version=_first_known(
            getattr(result, "adapter_version", ""),
            getattr(result, "tool_version", ""),
            getattr(environment, "adapter_version", ""),
        ),
        config_hash=_first_known(
            getattr(result, "effective_config_hash", ""),
            getattr(workflow, "config_hash", ""),
            getattr(workflow, "descriptor_hash", ""),
        ),
        evaluator_version=_first_known(
            getattr(result, "evaluator_version", ""), getattr(environment, "awb_version", "")
        ),
        execution_mode=_first_known(
            getattr(result, "execution_mode", ""), getattr(workflow, "mode", "")
        ),
        environment_fingerprint=_first_known(environment_fingerprint),
        budget_fingerprint=_first_known(getattr(result, "budget_fingerprint", "")),
    )


def identity_from_mapping(data: dict) -> CohortIdentity:
    workflow = data.get("workflow") or {}
    environment = data.get("environment") or {}
    environment_fingerprint = data.get("environment_fingerprint", "")
    cohort_manifest = data.get("cohort_manifest") or {}
    if not _known(environment_fingerprint) and _known(environment.get("pip_freeze_hash")):
        environment_fingerprint = "|".join(
            str(environment.get(name, ""))
            for name in ("os", "hardware", "python_version", "pip_freeze_hash")
        )
    return CohortIdentity(
        task_set_hash=_first_known(data.get("task_set_hash"), cohort_manifest.get("task_set_hash")),
        selection_identity=_selection_identity(cohort_manifest),
        model=_first_known(data.get("model"), workflow.get("model")),
        adapter_version=_first_known(
            data.get("adapter_version"),
            data.get("tool_version"),
            environment.get("adapter_version"),
        ),
        config_hash=_first_known(
            data.get("effective_config_hash"),
            workflow.get("config_hash"),
            workflow.get("descriptor_hash"),
        ),
        evaluator_version=_first_known(
            data.get("evaluator_version"), environment.get("awb_version")
        ),
        execution_mode=_first_known(data.get("execution_mode"), workflow.get("mode")),
        environment_fingerprint=_first_known(environment_fingerprint),
        budget_fingerprint=_first_known(data.get("budget_fingerprint")),
    )


def cohort_group_key(result) -> str:
    identity = identity_from_result(result)
    if identity.eligible:
        return identity.cohort_id
    run_id = re.sub(r"_run\d+$", "", getattr(result, "run_id", "") or "unknown")
    return f"legacy:{result.tool}:{run_id}:{identity.cohort_id}"


def cohort_group_key_mapping(data: dict) -> str:
    identity = identity_from_mapping(data)
    if identity.eligible:
        return identity.cohort_id
    run_id = re.sub(r"_run\d+$", "", data.get("run_id", "") or "unknown")
    return f"legacy:{data.get('tool', 'unknown')}:{run_id}:{identity.cohort_id}"


@dataclass(frozen=True)
class CohortCoverage:
    eligible: bool
    reasons: list[str]
    selected_task_ids: list[str]
    requested_repeats: int | None
    observed_attempts: dict[str, int]


def _value(row, name: str, default=None):
    return row.get(name, default) if isinstance(row, dict) else getattr(row, name, default)


def _manifest(row) -> dict:
    value = _value(row, "cohort_manifest", {})
    return value if isinstance(value, dict) else {}


def assess_cohort_coverage(rows: list) -> CohortCoverage:
    """Require one complete, balanced task-repeat grid with stable task definitions."""
    if not rows:
        return CohortCoverage(False, ["empty cohort"], [], None, {})

    identities = [
        identity_from_mapping(row) if isinstance(row, dict) else identity_from_result(row)
        for row in rows
    ]
    reasons = [f"missing {name}" for name in identities[0].missing_fields]
    if any(identity != identities[0] for identity in identities[1:]):
        reasons.append("mixed cohort identity")

    manifests = [_manifest(row) for row in rows]
    selected = manifests[0].get("selected_task_ids")
    repeats = manifests[0].get("requested_repeats")
    if (
        not isinstance(selected, list)
        or not selected
        or any(not isinstance(t, str) for t in selected)
    ):
        selected = []
    else:
        if len(set(selected)) != len(selected):
            reasons.append("duplicate task in planned selection")
        selected = sorted(set(selected))
    if type(repeats) is not int or repeats <= 0:
        repeats = None

    counts = Counter(str(_value(row, "task_id", "")) for row in rows)
    if not selected or repeats is None:
        reasons.append("missing planned task-repeat grid")
    else:
        expected = Counter({task_id: repeats for task_id in selected})
        if counts != expected:
            reasons.append("incomplete or unbalanced task-repeat grid")

    hashes: dict[str, set[str]] = defaultdict(set)
    repeat_identities: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        task_id = str(_value(row, "task_id", ""))
        definition_hash = _value(row, "task_definition_hash", "")
        if _known(definition_hash):
            hashes[task_id].add(str(definition_hash))
        else:
            reasons.append(f"missing task definition hash for {task_id or 'unknown task'}")
        repeat_index = _value(row, "repeat_index")
        if type(repeat_index) is not int:
            match = re.search(r"_run(\d+)$", str(_value(row, "run_id", "")))
            repeat_index = int(match.group(1)) if match else None
        if type(repeat_index) is int:
            repeat_identities[task_id].append(repeat_index)
    if any(len(values) != 1 for values in hashes.values()):
        reasons.append("task definition changed within cohort")
    if repeats is not None:
        expected_repeats = list(range(1, repeats + 1))
        for task_id in selected:
            observed = sorted(repeat_identities.get(task_id, []))
            if observed and observed != expected_repeats:
                reasons.append(f"invalid repeat identities for {task_id}")
            elif repeats > 1 and not observed:
                reasons.append(f"missing repeat identities for {task_id}")

    unique_reasons = sorted(set(reasons))
    return CohortCoverage(
        eligible=not unique_reasons,
        reasons=unique_reasons,
        selected_task_ids=selected,
        requested_repeats=repeats,
        observed_attempts=dict(sorted(counts.items())),
    )
