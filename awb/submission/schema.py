"""Submission data structures and hardware classification."""

from __future__ import annotations

from dataclasses import dataclass, field

HARDWARE_CLASSES = {
    "apple_m1_16gb": "Apple M1, 16GB",
    "apple_m2_16gb": "Apple M2, 16GB",
    "apple_m2_24gb": "Apple M2, 24GB",
    "apple_m3_36gb": "Apple M3 Pro/Max, 36GB",
    "apple_m3_18gb": "Apple M3, 18GB",
    "apple_m4_16gb": "Apple M4, 16GB",
    "apple_m4_24gb": "Apple M4 Pro, 24GB",
    "apple_m4_48gb": "Apple M4 Max, 48GB",
    "apple_m5_24gb": "Apple M5, 24GB",
    "apple_m5_48gb": "Apple M5 Pro/Max, 48GB",
    "desktop_16cpu_32gb": "Desktop, 16 CPU, 32GB",
    "desktop_32cpu_64gb": "Desktop, 32 CPU, 64GB",
    "cloud_4cpu_16gb": "Cloud, 4 vCPU, 16GB",
    "cloud_8cpu_32gb": "Cloud, 8 vCPU, 32GB",
    "cloud_16cpu_64gb": "Cloud, 16 vCPU, 64GB",
    "cloud_32cpu_128gb": "Cloud, 32 vCPU, 128GB",
    "other": "Other / Custom",
}

# Metrics that are comparable across hardware classes
HARDWARE_INDEPENDENT_METRICS = {
    "correctness",
    "cost_efficiency",
    "code_quality",
    "reliability",
    "security",
}

# Metrics that require same hardware class for fair comparison
HARDWARE_DEPENDENT_METRICS = {"speed", "efficiency"}


@dataclass
class SubmissionTool:
    name: str
    version: str
    config_description: str = ""


@dataclass
class SubmissionModel:
    name: str = ""
    provider: str = ""
    input_per_m_tokens: float = 0.0
    output_per_m_tokens: float = 0.0


@dataclass
class SubmissionEnvironment:
    os: str = ""
    hardware_class: str = "other"
    hardware_detail: str = ""
    network: str = "local"


@dataclass
class SubmissionRunOutcome:
    success: bool = False
    partial_credit_score: float = 0.0
    partial_credit_max: float = 0.0


@dataclass
class SubmissionRunMetrics:
    wall_clock_seconds: float = 0.0
    iteration_count: int = 0
    human_interventions: int = 0
    files_modified: int = 0
    lines_changed: int = 0


@dataclass
class SubmissionRunCost:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    estimated_credits: float | None = None


@dataclass
class SubmissionRunQuality:
    lint_delta: int = 0
    security_delta: int = 0
    test_regressions: int = 0


@dataclass
class SubmissionRun:
    run_number: int
    outcome: SubmissionRunOutcome
    metrics: SubmissionRunMetrics
    cost: SubmissionRunCost
    quality: SubmissionRunQuality
    timestamp: str = ""


@dataclass
class SubmissionTaskResult:
    task_id: str
    runs: list[SubmissionRun] = field(default_factory=list)


@dataclass
class Submission:
    spec_version: str
    tool: SubmissionTool
    model: SubmissionModel
    environment: SubmissionEnvironment
    awb_version: str
    task_set_hash: str
    submitter: str
    results: list[SubmissionTaskResult] = field(default_factory=list)
