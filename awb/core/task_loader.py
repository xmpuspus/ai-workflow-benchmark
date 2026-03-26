from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate

from awb.core.config import (
    TASK_SCHEMA_PATH,
    TASKS_DIR,
    PartialCreditCriterion,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)

logger = logging.getLogger(__name__)


def _load_schema() -> dict:
    with TASK_SCHEMA_PATH.open() as f:
        return json.load(f)


def _parse_task(raw: dict) -> TaskDefinition:
    repo_raw = raw["repo"]
    repo = TaskRepo(
        url=repo_raw["url"],
        commit=repo_raw["commit"],
        setup_commands=repo_raw.get("setup_commands") or [],
    )

    verif_raw = raw.get("verification") or {}
    partial_credit = [
        PartialCreditCriterion(
            criterion=pc["criterion"],
            points=pc["points"],
            check=pc["check"],
        )
        for pc in (verif_raw.get("partial_credit") or [])
    ]
    verification = TaskVerification(
        test_commands=verif_raw.get("test_commands") or [],
        lint_commands=verif_raw.get("lint_commands") or [],
        security_commands=verif_raw.get("security_commands") or [],
        partial_credit=partial_credit,
    )

    constraints_raw = raw.get("constraints") or {}
    constraints = TaskConstraints(
        max_iterations=constraints_raw.get("max_iterations", 20),
        timeout_seconds=constraints_raw.get("timeout_seconds", 1800),
    )

    issue_raw = raw.get("issue") or {}

    return TaskDefinition(
        id=raw["id"],
        category=raw["category"],
        title=raw["title"],
        difficulty=raw["difficulty"],
        estimated_minutes=raw["estimated_minutes"],
        languages=raw["languages"],
        tags=raw.get("tags") or [],
        capabilities=raw.get("capabilities") or [],
        repo=repo,
        verification=verification,
        constraints=constraints,
        issue_description=issue_raw.get("description", ""),
        files_to_examine=issue_raw.get("files_to_examine") or [],
        workspace_claude_md=raw.get("workspace_claude_md", ""),
    )


def load_task(path: Path) -> TaskDefinition:
    with path.open() as f:
        raw = yaml.safe_load(f)
    schema = _load_schema()
    validate(instance=raw, schema=schema)
    return _parse_task(raw)


def load_all_tasks(
    tasks_dir: Path | None = None,
    category: str | None = None,
) -> list[TaskDefinition]:
    root = tasks_dir or TASKS_DIR
    paths = sorted(p for p in root.glob("**/*.yaml") if not p.name.startswith("_"))
    tasks = []
    for path in paths:
        try:
            task = load_task(path)
        except ValidationError as e:
            logger.warning("Skipping %s: schema validation failed: %s", path.name, e.message)
            continue
        except yaml.YAMLError as e:
            logger.warning("Skipping %s: YAML parse error: %s", path.name, e)
            continue
        if category is None or task.category == category:
            tasks.append(task)
    return tasks


def validate_task_yaml(path: Path) -> list[str]:
    errors = []
    try:
        with path.open() as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    schema = _load_schema()
    try:
        validate(instance=raw, schema=schema)
    except ValidationError as e:
        errors.append(e.message)

    # Check partial credit sums to 100
    pc = (raw or {}).get("verification", {}).get("partial_credit", [])
    if pc:
        total = sum(c.get("points", 0) for c in pc)
        if total != 100:
            errors.append(f"partial_credit points sum to {total}, expected 100")

    return errors
