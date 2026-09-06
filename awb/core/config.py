from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from importlib.resources import files as _pkg_files

    _TASKS_PKG = _pkg_files("awb.tasks")
    TASKS_DIR = Path(str(_TASKS_PKG))
except (ImportError, TypeError, FileNotFoundError):
    TASKS_DIR = Path(__file__).parent.parent / "tasks"

RESULTS_DIR = Path(os.environ.get("AWB_RESULTS_DIR", Path.cwd() / "results" / "runs"))
TASK_SCHEMA_PATH = TASKS_DIR / "schema.json"
RESULT_SCHEMA_PATH = RESULTS_DIR / "schema.json"
# Always-bundled copy of the v2 result schema (lives next to awb/__init__.py).
PKG_RESULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "results-schema.json"


@dataclass
class TaskRepo:
    url: str
    commit: str
    setup_commands: list[str] = field(default_factory=list)


@dataclass
class PartialCreditCriterion:
    criterion: str
    points: int
    check: str


@dataclass
class TaskVerification:
    test_commands: list[str] = field(default_factory=list)
    lint_commands: list[str] = field(default_factory=list)
    security_commands: list[str] = field(default_factory=list)
    partial_credit: list[PartialCreditCriterion] = field(default_factory=list)


@dataclass
class TaskConstraints:
    max_iterations: int = 20
    timeout_seconds: int = 1800
    max_input_tokens: int = 0  # 0 = unlimited
    max_output_tokens: int = 0  # 0 = unlimited


@dataclass
class TaskProvenance:
    source_pr_url: str = ""
    created_at: str = ""
    last_verified_at: str = ""


@dataclass
class TaskDefinition:
    id: str
    category: str
    title: str
    difficulty: str
    estimated_minutes: int
    languages: list[str]
    repo: TaskRepo
    verification: TaskVerification
    constraints: TaskConstraints
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    issue_description: str = ""
    files_to_examine: list[str] = field(default_factory=list)
    allowed_edit_paths: list[str] = field(default_factory=list)
    workspace_claude_md: str = ""
    provenance: TaskProvenance | None = None
    contamination_risk: str = "unknown"
    label: str = "synthetic_overlay"


@dataclass
class CriterionResult:
    criterion: str
    points_earned: float
    points_possible: float
    passed: bool


@dataclass
class RunError:
    """Captured exception info for runs that failed unexpectedly.

    Distinguishes "ran to completion with score=0" from "crashed with a
    Python exception". Surfaced in RunOutcome.error so the consumer can tell
    the two apart.
    """

    exc_type: str = ""
    exc_message: str = ""
    traceback_tail: str = ""


@dataclass
class RunOutcome:
    success: bool
    partial_credit_score: float
    partial_credit_max: float
    breakdown: list[CriterionResult] = field(default_factory=list)
    error: RunError | None = None


@dataclass
class RunMetrics:
    wall_clock_seconds: float = 0.0
    iteration_count: int = 0
    human_interventions: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    files_modified: int = 0
    lines_changed: int = 0


@dataclass
class RunCost:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_tokens: int = 0
    estimated_cost_usd: float = 0.0
    estimated_credits: float | None = None
    usage_status: str = "unknown"


@dataclass
class RunQuality:
    lint_delta: int = 0
    security_delta: int = 0
    test_regressions: int = 0
    baseline_security_issues: int | None = None
    post_security_issues: int | None = None
    lint_status: str = "missing"
    security_status: str = "missing"
    test_regressions_status: str = "missing"


@dataclass
class RunExecution:
    status: str = "unknown"
    stage: str = "pending"
    termination_reason: str = ""
    tool_success: bool | None = None
    tool_exit_code: int | None = None


def _detect_python_version() -> str:
    import sys

    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _detect_awb_version() -> str:
    try:
        import awb

        return awb.__version__
    except Exception:
        return ""


def _pip_freeze_hash() -> str:
    """SHA-256 prefix of `pip freeze` output for reproducibility."""
    import hashlib

    try:
        out = subprocess.check_output(
            ["pip", "freeze"], text=True, timeout=15, stderr=subprocess.DEVNULL
        )
        lines = sorted(line for line in out.splitlines() if line.strip())
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""


def _detect_hardware() -> str:
    system = platform.system()
    if system == "Darwin":
        try:
            chip = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            ).strip()
            mem_bytes = int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                ).strip()
            )
            mem_gb = mem_bytes // (1024**3)
            return f"{chip}, {mem_gb}GB"
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
    return platform.machine()


@dataclass
class RunEnvironment:
    os: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    hardware: str = field(default_factory=_detect_hardware)
    python_version: str = field(default_factory=_detect_python_version)
    awb_version: str = field(default_factory=_detect_awb_version)
    adapter_version: str = ""
    pip_freeze_hash: str = field(default_factory=_pip_freeze_hash)


@dataclass
class WorkflowInfo:
    name: str = ""
    descriptor_hash: str = ""
    tool: str = ""
    model: str = ""
    mode: str = ""
    config_hash: str = ""


@dataclass
class RunResult:
    task_id: str
    tool: str
    run_id: str
    timestamp: str
    outcome: RunOutcome
    metrics: RunMetrics
    cost: RunCost
    quality: RunQuality
    environment: RunEnvironment
    tool_version: str = ""
    model: str = ""
    workflow: WorkflowInfo | None = None
    task_set_hash: str = ""
    trace_path: str = ""
    execution: RunExecution = field(default_factory=RunExecution)
    task_definition_hash: str = ""
    evaluator_version: str = ""
    effective_config_hash: str = ""
    adapter_version: str = ""
    execution_mode: str = "host"
    environment_fingerprint: str = ""
    budget_fingerprint: str = ""
    cohort_id: str = ""
    loaded_instruction_files: list[str] = field(default_factory=list)
    allowed_edit_paths: list[str] = field(default_factory=list)
    effective_input_manifest: dict[str, Any] = field(default_factory=dict)
    environment_manifest: dict[str, Any] = field(default_factory=dict)
    cohort_manifest: dict[str, Any] = field(default_factory=dict)
    experiment_plan_hash: str = ""
    experiment_split: str = ""
    experiment_arm: str = ""
    repeat_index: int | None = None
    requested_model: str = ""
    experiment_attempt_status: str = ""
    experiment_state_policy: str = ""
    configured_instruction_files: list[str] = field(default_factory=list)

    @property
    def execution_status(self) -> str:
        return self.execution.status

    @property
    def execution_stage(self) -> str:
        return self.execution.stage

    @property
    def termination_reason(self) -> str:
        return self.execution.termination_reason

    @property
    def usage_status(self) -> str:
        return self.cost.usage_status

    def to_dict(self) -> dict[str, Any]:
        breakdown = [
            {
                "criterion": c.criterion,
                "points_earned": c.points_earned,
                "points_possible": c.points_possible,
                "passed": c.passed,
            }
            for c in self.outcome.breakdown
        ]
        d = {
            "task_id": self.task_id,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "model": self.model,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "outcome": {
                "success": self.outcome.success,
                "partial_credit_score": self.outcome.partial_credit_score,
                "partial_credit_max": self.outcome.partial_credit_max,
                "breakdown": breakdown,
                **(
                    {
                        "error": {
                            "exc_type": self.outcome.error.exc_type,
                            "exc_message": self.outcome.error.exc_message,
                            "traceback_tail": self.outcome.error.traceback_tail,
                        }
                    }
                    if self.outcome.error
                    else {}
                ),
            },
            "metrics": {
                "wall_clock_seconds": self.metrics.wall_clock_seconds,
                "iteration_count": self.metrics.iteration_count,
                "human_interventions": self.metrics.human_interventions,
                "tool_calls": self.metrics.tool_calls,
                "files_modified": self.metrics.files_modified,
                "lines_changed": self.metrics.lines_changed,
            },
            "cost": {
                "input_tokens": self.cost.input_tokens,
                "output_tokens": self.cost.output_tokens,
                "cache_read_tokens": self.cost.cache_read_tokens,
                "cache_creation_tokens": self.cost.cache_creation_tokens,
                "thinking_tokens": self.cost.thinking_tokens,
                "estimated_cost_usd": self.cost.estimated_cost_usd,
                "usage_status": self.cost.usage_status,
                **(
                    {"estimated_credits": self.cost.estimated_credits}
                    if self.cost.estimated_credits is not None
                    else {}
                ),
            },
            "quality": {
                "lint_delta": self.quality.lint_delta,
                "security_delta": self.quality.security_delta,
                "test_regressions": self.quality.test_regressions,
                "baseline_security_issues": self.quality.baseline_security_issues,
                "post_security_issues": self.quality.post_security_issues,
                "lint_status": self.quality.lint_status,
                "security_status": self.quality.security_status,
                "test_regressions_status": self.quality.test_regressions_status,
            },
            "environment": {
                "os": self.environment.os,
                "hardware": self.environment.hardware,
                "python_version": self.environment.python_version,
                "awb_version": self.environment.awb_version,
                "adapter_version": self.environment.adapter_version,
                "pip_freeze_hash": self.environment.pip_freeze_hash,
            },
            "execution": {
                "status": self.execution.status,
                "stage": self.execution.stage,
                "termination_reason": self.execution.termination_reason,
                "tool_success": self.execution.tool_success,
                "tool_exit_code": self.execution.tool_exit_code,
            },
            "task_definition_hash": self.task_definition_hash,
            "evaluator_version": self.evaluator_version,
            "effective_config_hash": self.effective_config_hash,
            "adapter_version": self.adapter_version,
            "execution_mode": self.execution_mode,
            "environment_fingerprint": self.environment_fingerprint,
            "budget_fingerprint": self.budget_fingerprint,
            "cohort_id": self.cohort_id,
            "loaded_instruction_files": self.loaded_instruction_files,
            "allowed_edit_paths": self.allowed_edit_paths,
            "effective_input_manifest": self.effective_input_manifest,
            "environment_manifest": self.environment_manifest,
            "cohort_manifest": self.cohort_manifest,
        }
        if self.workflow:
            d["workflow"] = {
                "name": self.workflow.name,
                "descriptor_hash": self.workflow.descriptor_hash,
                "tool": self.workflow.tool,
                "model": self.workflow.model,
                "mode": self.workflow.mode,
                "config_hash": self.workflow.config_hash,
            }
        if self.task_set_hash:
            d["task_set_hash"] = self.task_set_hash
        if self.trace_path:
            d["trace_path"] = self.trace_path
        if self.experiment_plan_hash:
            for name in (
                "experiment_plan_hash",
                "experiment_split",
                "experiment_arm",
                "repeat_index",
                "requested_model",
                "experiment_attempt_status",
                "experiment_state_policy",
                "configured_instruction_files",
            ):
                d[name] = getattr(self, name)
        return d
