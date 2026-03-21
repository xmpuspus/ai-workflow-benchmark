# AI Workflow Benchmark (awb)

Benchmark harness measuring AI coding tool+workflow performance, not just model capability.

## The Problem

Existing benchmarks test models in isolation:

- **SWE-bench** - 500 tasks, Python-only, headless model evaluation. No iteration cycles, no cost tracking, no human interventions.
- **Aider Polyglot** - 225 Exercism problems, measures edit formats and context strategies. Still model-centric.

Neither measures the tool+workflow. A developer using Claude Code with a well-tuned CLAUDE.md, custom hooks, and a structured workflow will outperform the same model running vanilla. No benchmark captures that gap.

AWB benchmarks the full stack: tool, configuration, workflow, and model together.

## What This Measures

Seven scoring dimensions per task run, using sigmoid normalization with per-task baselines:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Correctness | 55% | Combined success rate (pass/fail) + partial credit (rubric-based) |
| Cost efficiency | 15% | Estimated USD per task, normalized per difficulty tier |
| Speed | 10% | Wall-clock seconds, baseline derived from task estimated_minutes |
| Code quality | 10% | Lint warning delta before/after (ruff, eslint, tsc) |
| Reliability | 5% | Pre-existing tests broken by the change |
| Security | 3% | New security issues introduced (bandit, semgrep) |
| Efficiency | 2% | Tool turns used relative to task max_iterations |

All metrics use sigmoid normalization: optimal performance scores ~95, baseline scores ~50, and scores never go negative. Per-task baselines are derived from difficulty level and constraints.

### Capability Profiles

Each task maps to 1-3 capabilities, producing a radar chart of tool strengths:

- **Code comprehension** - understanding existing code (27 tasks)
- **Bug diagnosis** - finding root cause (17 tasks)
- **Multi-file reasoning** - coordinated changes across files (20 tasks)
- **Framework knowledge** - knowing APIs and patterns (26 tasks)
- **Test writing** - writing correct tests (8 tasks)
- **Refactoring discipline** - change without breaking (23 tasks)
- **Security awareness** - identifying vulnerabilities (8 tasks)
- **Cost discipline** - token efficiency (derived from all tasks)

## Task Suite

60 tasks across 7 categories, built on real open-source frameworks:

| Category | Tasks | Easy/Med/Hard | What It Tests |
|----------|-------|---------------|---------------|
| Bug Fix | 10 | 3/3/2 | Root cause analysis, None handling, async bugs, race conditions |
| Feature Addition | 8 | 2/3/2 | Convention adherence, middleware patterns, cross-cutting features |
| Refactoring | 10 | 2/3/2 | Multi-file consistency, pattern extraction, async migration |
| Code Review | 7 | 2/3/1 | Security awareness, OWASP, concurrency bugs, CORS/auth |
| Debugging | 7 | 2/1/3 | Hypothesis testing, connection leaks, pipeline tracing |
| Multi-File | 8 | 0/3/3 | Cross-module architecture, plugin systems, auth chains |
| Legacy Code | 10 | 4/4/2 | Modernization, migration, dead code removal, type annotations |

Repos used: FastAPI, httpx, Flask, Starlette, Click, Pydantic, Hono.

All repos pinned to release tag SHAs. Setup installs via venv + pip (Python) or npm (TypeScript) in under 15 seconds.

## Quick Start

```bash
pip install -e ".[dev]"

# Optional: install scipy/numpy for advanced statistics
pip install -e ".[stats]"
```

### Check available tools

```bash
awb tools
```

### Validate task definitions

```bash
awb validate
```

### Run a benchmark

```bash
# Run vanilla vs custom on all tasks (default: 3 runs each)
awb run --runs 1

# Single tool, single task
awb run claude-code-custom -t BF-001 --runs 1

# Filter by category
awb run --runs 1 --category legacy-code

# Preview what will execute
awb run --dry-run
```

### Analyze capability gaps

```bash
awb gap results/runs/<run_dir>/
```

Output includes:
- Capability radar chart (per-dimension scores)
- Failure analysis with root cause classification
- Systematic weakness detection (e.g., "fails all hard tasks")
- Actionable improvement suggestions

### Compare results

```bash
awb compare results/runs/<run1>/ results/runs/<run2>/
```

### External submissions

```bash
# Validate a submission from another tool/user
awb submit submission.json

# Compare two external submissions with statistical significance
awb compare-submissions submission_a.json submission_b.json
```

### Workflow descriptors

```bash
awb workflow export claude-code-custom -n "my-setup"
awb workflow validate workflow.yaml
awb workflow diff baseline.yaml optimized.yaml
awb workflow init
```

### Generate leaderboard

```bash
awb leaderboard
awb leaderboard --output-dir ./site
```

## Architecture

```
awb/core/           Config, task loading, runner, result recording, repo management
awb/adapters/       Tool adapters (implement ToolAdapter ABC)
awb/verification/   Diff analysis, lint checking, partial credit evaluation
awb/scoring/        Sigmoid normalization, per-task baselines, capability profiles,
                    statistics (confidence intervals, significance testing),
                    integrity checks (contamination detection)
awb/analysis/       Gap analysis engine, workflow improvement suggestions
awb/submission/     External submission format, cross-submission comparison
awb/workflow/       Workflow descriptors (export, validate, diff)
awb/leaderboard/    Static HTML leaderboard generator
awb/tasks/          60 task YAML definitions, organized by category
awb/cli.py          Click-based CLI interface
results/            Run outputs (gitignored), JSON schemas
```

## Scoring System (v2)

### Sigmoid normalization

All metrics use a sigmoid curve centered at the task's baseline:
- At the **optimal** value (excellent performance): score ~95
- At the **baseline** value (adequate performance): score ~50
- Scores never go negative, providing smooth gradient at all values

Per-task baselines are derived from difficulty:

| Metric | Easy | Medium | Hard |
|--------|------|--------|------|
| Cost optimal/baseline | $0.05/$0.30 | $0.20/$1.00 | $1.00/$3.00 |
| Speed | 50%/100% of estimated_minutes | same | same |
| Iterations | 3/max_iters | 8/max_iters | 15/max_iters |

### Difficulty-weighted aggregation

Aggregate scores weight by difficulty: easy=1.0, medium=1.5, hard=2.5. Solving hard tasks counts more than solving easy ones.

### Configurable weight profiles

Three built-in profiles in `awb/scoring/weights.yaml`:
- **default** - balanced (correctness 55%, cost 15%, speed 10%, quality 10%)
- **correctness_focused** - correctness 70%, everything else reduced
- **production** - higher weight on reliability (10%) and security (8%)

### Statistical framework

- Confidence intervals via t-distribution (no scipy required)
- Significance testing via sign test for tool comparison
- Integrity checks: contamination detection (suspiciously fast completions), variance anomalies (identical times across runs)
- Minimum 3 runs recommended for stable scores

## Adding Tasks

Tasks are YAML files under `awb/tasks/<category>/`. Copy `awb/tasks/_template.yaml`:

```yaml
id: BF-042
category: bug-fix
title: "Fix response_model silently dropping extra fields in FastAPI"
difficulty: easy
estimated_minutes: 15
languages: [python]
tags: [fastapi, pydantic, validation]
capabilities: [framework_knowledge, test_writing]

repo:
  url: "https://github.com/tiangolo/fastapi"
  commit: "628c34e0"
  setup_commands:
    - "python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[all]'"

issue:
  description: |
    The endpoint's response_model silently strips extra fields...
  files_to_examine:
    - "fastapi/routing.py"

verification:
  test_commands:
    - "source .venv/bin/activate && python3 -m pytest tests/test_extra_fields.py -v"
  lint_commands:
    - "source .venv/bin/activate && ruff check tests/test_extra_fields.py"
  partial_credit:
    - criterion: "Uses Pydantic v2 ConfigDict"
      points: 50
      check: "grep -q 'ConfigDict' tests/test_extra_fields.py"
    - criterion: "Tests pass"
      points: 50
      check: "source .venv/bin/activate && python3 -m pytest tests/test_extra_fields.py -v"

constraints:
  max_iterations: 20
  timeout_seconds: 1800
```

Valid capabilities: `code_comprehension`, `bug_diagnosis`, `multi_file_reasoning`, `framework_knowledge`, `test_writing`, `refactoring_discipline`, `security_awareness`.

Full schema: `awb/tasks/schema.json`

## Adding Tools

Create a new file in `awb/adapters/` implementing the `ToolAdapter` ABC:

```python
from awb.adapters.base import ToolAdapter, ToolResult
from pathlib import Path

class MyToolAdapter(ToolAdapter):
    name = "my-tool"
    display_name = "My Tool"

    async def execute(self, prompt: str, workspace: Path,
                      max_turns: int = 20, timeout_seconds: int = 1800) -> ToolResult:
        ...

    def check_available(self) -> bool:
        ...

    def get_config_hash(self) -> str:
        ...
```

Register it in `awb/adapters/registry.py`.

## External Submissions

Anyone can submit results using the JSON format defined in `results/submission-schema.json`:

```bash
awb submit my-results.json              # validate and display
awb compare-submissions a.json b.json   # compare with significance testing
```

The submission format includes tool info, model pricing, hardware class, and per-task run results. Hardware classes enable fair speed comparisons (only compared within the same tier).

## Fair Comparison Methodology

Full details: [METHODOLOGY.md](METHODOLOGY.md)

1. Same prompt - identical task description to every tool
2. Same starting state - fresh git clone at pinned commit
3. Same timeout - equal wall-clock limit per task
4. Same verification - identical test suite and rubric
5. Tool-native features allowed - hooks, agents, IDE autocomplete all fair game
6. 3 runs minimum - report median to reduce variance
7. Version pinning - tool, model, and repo commits all recorded
8. Open methodology - all code, prompts, and scoring logic open source
9. Known limitations stated explicitly

## License

MIT
