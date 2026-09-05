"""Comparison cohort identity and conservative eligibility checks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CohortIdentity:
    task_set_hash: str = ""
    model: str = ""
    adapter_version: str = ""
    config_hash: str = ""
    evaluator_version: str = ""
    execution_mode: str = ""
    environment_fingerprint: str = ""
    budget_fingerprint: str = ""

    @property
    def missing_fields(self) -> list[str]:
        return [name for name, value in asdict(self).items() if not value]

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
    if not environment_fingerprint and getattr(environment, "pip_freeze_hash", ""):
        environment_fingerprint = "|".join(
            [
                environment.os,
                environment.hardware,
                environment.python_version,
                environment.pip_freeze_hash,
            ]
        )
    return CohortIdentity(
        task_set_hash=getattr(result, "task_definition_hash", "")
        or getattr(result, "task_set_hash", ""),
        model=getattr(result, "model", "") or getattr(workflow, "model", ""),
        adapter_version=getattr(result, "tool_version", "")
        or getattr(environment, "adapter_version", ""),
        config_hash=getattr(result, "effective_config_hash", "")
        or getattr(workflow, "config_hash", "")
        or getattr(workflow, "descriptor_hash", ""),
        evaluator_version=getattr(result, "evaluator_version", "")
        or getattr(environment, "awb_version", ""),
        execution_mode=getattr(result, "execution_mode", "") or getattr(workflow, "mode", ""),
        environment_fingerprint=environment_fingerprint,
        budget_fingerprint=getattr(result, "budget_fingerprint", ""),
    )


def identity_from_mapping(data: dict) -> CohortIdentity:
    workflow = data.get("workflow") or {}
    environment = data.get("environment") or {}
    environment_fingerprint = data.get("environment_fingerprint", "")
    if not environment_fingerprint and environment.get("pip_freeze_hash"):
        environment_fingerprint = "|".join(
            str(environment.get(name, ""))
            for name in ("os", "hardware", "python_version", "pip_freeze_hash")
        )
    return CohortIdentity(
        task_set_hash=data.get("task_definition_hash") or data.get("task_set_hash", ""),
        model=data.get("model") or workflow.get("model", ""),
        adapter_version=data.get("tool_version") or environment.get("adapter_version", ""),
        config_hash=data.get("effective_config_hash")
        or workflow.get("config_hash")
        or workflow.get("descriptor_hash", ""),
        evaluator_version=data.get("evaluator_version") or environment.get("awb_version", ""),
        execution_mode=data.get("execution_mode") or workflow.get("mode", ""),
        environment_fingerprint=environment_fingerprint,
        budget_fingerprint=data.get("budget_fingerprint", ""),
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
