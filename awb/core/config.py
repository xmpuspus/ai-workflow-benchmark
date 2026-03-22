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

def _load_default_weights() -> dict[str, float]:
    """Load default metric weights from scoring/weights.yaml."""
    from awb.scoring.composite import load_weight_profile
    return load_weight_profile("default")


# Lazy-loaded on first access via report.py and leaderboard — kept as dict for backward compat
METRIC_WEIGHTS: dict[str, float] = {
    "correctness": 0.55,
    "cost_efficiency": 0.15,
    "speed": 0.10,
    "code_quality": 0.10,
    "reliability": 0.05,
    "security": 0.03,
    "efficiency": 0.02,
}


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


@dataclass
class CriterionResult:
    criterion: str
    points_earned: float
    points_possible: float
    passed: bool


@dataclass
class RunOutcome:
    success: bool
    partial_credit_score: float
    partial_credit_max: float
    breakdown: list[CriterionResult] = field(default_factory=list)


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
    estimated_cost_usd: float = 0.0


@dataclass
class RunQuality:
    lint_delta: int = 0
    security_delta: int = 0
    test_regressions: int = 0


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
                "estimated_cost_usd": self.cost.estimated_cost_usd,
            },
            "quality": {
                "lint_delta": self.quality.lint_delta,
                "security_delta": self.quality.security_delta,
                "test_regressions": self.quality.test_regressions,
            },
            "environment": {
                "os": self.environment.os,
                "hardware": self.environment.hardware,
            },
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
        return d
