<div align="center">
  <h1>AI Workflow Benchmark (AWB)</h1>
  <p><strong>Measure AI coding tool+workflow performance, not just model capability.</strong></p>
  <p>
    <a href="https://pypi.org/project/awb/"><img src="https://img.shields.io/badge/pypi-v1.0.0-blue" alt="PyPI"></a>
    <a href="https://github.com/xmpuspus/ai-workflow-benchmark/actions"><img src="https://img.shields.io/github/actions/workflow/status/xmpuspus/ai-workflow-benchmark/test.yml" alt="Tests"></a>
    <img src="https://img.shields.io/badge/tasks-100-blue" alt="Tasks">
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  </p>
  <br/>
  <img src="demos/awb-showcase.gif" alt="AWB Demo — install, validate, run, analyze" width="680"/>
  <br/>
  <sub>Install from PyPI, validate 100 tasks, run vanilla vs custom, get capability profiles and improvement suggestions.</sub>
</div>

---

## Why This Exists

SWE-bench tests models. AWB tests workflows. The same model running vanilla Claude Code vs. a purpose-built setup with a tuned CLAUDE.md, hooks, and structured agents produces meaningfully different results on real engineering tasks. No existing benchmark captures that gap — they all evaluate the model in isolation.

AWB benchmarks the full stack: **tool + configuration + workflow + model**, together, on 100 tasks drawn from real open-source repositories.

## Quick Start

```bash
pip install awb

awb quickstart                              # verify your setup
awb run --runs 3 --parallel --adaptive      # full 100-task benchmark (parallel, smart re-runs)
awb run --category workflow --runs 1        # workflow tasks only (quick test)
awb gap results/runs/<run_dir>/             # analyze capability gaps
```

## How It Works

```
Clone repo at pinned SHA
  → Run setup commands
  → Capture baseline lint/security counts
  → Execute tool with task prompt
  → Run test suite + partial credit rubric
  → Sigmoid-normalize 7 metrics
  → Produce weighted composite + capability profile
```

Each task starts from a fresh `git clone` at a pinned commit. Every tool gets the same prompt, the same timeout, and the same verification suite. Results are scored with sigmoid normalization so scores are never negative and never collapse at the boundary.

## Scoring System

Seven dimensions, sigmoid-normalized with per-task baselines derived from difficulty:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Correctness | 55% | Pass/fail (60%) + partial credit rubric (40%) |
| Cost efficiency | 15% | Estimated USD per task |
| Speed | 10% | Wall-clock seconds vs. estimated task time |
| Code quality | 10% | Lint warning delta (pre vs. post) |
| Reliability | 5% | Pre-existing tests broken by the change |
| Security | 3% | New security issues introduced |
| Efficiency | 2% | Tool turns used vs. task max |

**Sigmoid curve:** `score = 100 / (1 + exp(k * (value - baseline)))`

- Optimal performance (excellent) → ~95
- Baseline performance (adequate) → ~50
- Above baseline → smooth decay, never negative

**Difficulty-weighted aggregation:** hard tasks count 2.5×, medium 1.5×, easy 1.0×. A tool that solves hard tasks beats one that only solves easy ones even if the easy-task count is higher.

**Per-task baselines by difficulty:**

| Metric | Easy | Medium | Hard |
|--------|------|--------|------|
| Cost optimal / baseline | $0.05 / $0.30 | $0.20 / $1.00 | $1.00 / $3.00 |
| Speed | 50% / 100% of estimated_minutes | same | same |
| Iterations | 3 / max_iters | 8 / max_iters | 15 / max_iters |

## The 100 Tasks

Real open-source repos, pinned to release tag SHAs. Setup runs in under 15 seconds via venv + pip (Python) or npm (TypeScript).

| Category | Count | Easy / Med / Hard | What It Tests |
|----------|-------|-------------------|---------------|
| bug-fix | 12 | 7 / 1 / 4 | Root cause analysis, test-first diagnosis, N+1 queries |
| feature-addition | 9 | 3 / 0 / 6 | Convention adherence, ambiguous requirements, Dockerfiles, TypeScript typing |
| refactoring | 11 | 5 / 2 / 4 | Multi-file consistency, O(n^2) optimization, CI/CD config, async migration |
| code-review | 9 | 4 / 2 / 3 | Security review (report-only), concurrency analysis, migration guides, OWASP |
| debugging | 10 | 7 / 0 / 3 | Performance profiling, regression bisection, stack trace diagnosis |
| multi-file | 7 | 4 / 0 / 3 | Merge conflicts, plugin systems, auth chains |
| legacy-code | 12 | 9 / 0 / 3 | SQLAlchemy 2.0 migration, 20-file codebase navigation, dead code removal |
| workflow | 30 | 9 / 12 / 9 | Completeness tracking, convention discovery, security methodology, context utilization, async safety, config extraction, test-driven implementation |

**Repos used:** FastAPI, httpx, Flask, Starlette, Click, Pydantic, SQLAlchemy 2.0, Hono

**Task IDs:**
`BF-001–014` · `FA-001–010` · `RF-001–012` · `CR-001–010` · `DB-001–011` · `MF-001–009` · `LC-001–012` · `WF-001–030`

## Capability Profiles

Each task maps to 1–3 capabilities, producing a radar chart of tool strengths:

| Capability | Tasks | What It Measures |
|------------|-------|-----------------|
| code_comprehension | 41 | Understanding existing code before modifying |
| framework_knowledge | 35 | Knowing API patterns (Pydantic v2, async SQLAlchemy, etc.) |
| bug_diagnosis | 26 | Structured root cause analysis, test-first diagnosis |
| refactoring_discipline | 26 | Changing code without breaking behavior |
| multi_file_reasoning | 23 | Coordinating changes across multiple files |
| completeness_tracking | 10 | Following all requirements, not stopping at 80% |
| convention_adherence | 10 | Discovering and following project conventions |
| context_discovery | 10 | Reading project docs and config before editing |
| test_writing | 10 | Writing correct, meaningful tests |
| security_awareness | 10 | Identifying and fixing vulnerabilities |
| security_methodology | 10 | Applying security checklists systematically |
| cost_discipline | derived | Token efficiency across all tasks |

Example `awb gap` output:

```
Capability Profile
------------------
code_comprehension    ████████████████████  82.4  (n=27, conf=high)
framework_knowledge   ████████████████░░░░  68.1  (n=26, conf=high)
refactoring_discipline████████████████░░░░  65.3  (n=23, conf=high)
multi_file_reasoning  ████████████░░░░░░░░  51.2  (n=20, conf=high)
bug_diagnosis         ███████████████░░░░░  63.7  (n=17, conf=med)
test_writing          ██████████░░░░░░░░░░  44.1  (n=8,  conf=low)
security_awareness    █████████████░░░░░░░  55.8  (n=8,  conf=low)

Systematic Patterns
-------------------
- Fails 70%+ of multi_file_reasoning tasks → consider multi-agent workflows
- Token spend on failed hard tasks: $4.20 → add early-exit heuristics
- No failures on easy tasks → baseline is solid

Top Suggestions
---------------
1. Enable subagent mode for tasks spanning >3 files (impact: high)
2. Add repo-level CLAUDE.md with architecture overview (impact: medium)
3. Use --think flag for debugging tasks (impact: medium)
```

## Vanilla vs Custom

AWB ships two Claude Code adapters that run the same model with different configurations:

| | Vanilla | Custom |
|---|---|---|
| Hooks | Disabled | Your full hook suite |
| Skills | Disabled | Your registered skills |
| Auto-memory | Disabled | Active |
| System prompt | Generic | Default (loads CLAUDE.md) |

Both use the same model, same API, same task prompts. The only difference is whether your workflow automation (hooks, skills, memory) is active. This isolates the contribution of workflow configuration from model capability.

## Workflow Lift Score

When `awb run` executes both vanilla and custom (the default), it produces a **Workflow Lift** — a single number measuring how much your workflow configuration improves over the baseline:

```
Workflow Lift: +4.2 pts  (p=0.031, significant)
  Pass rate: vanilla 62% vs custom 68%
  Wins: custom 8 / vanilla 3 / ties 69

  Where your workflow helps:
    bug diagnosis             +12.3 pts  (17 tasks)
    multi file reasoning       +8.1 pts  (20 tasks)
    security awareness         +5.4 pts  (10 tasks)

  Where it hurts:
    cost discipline            -4.2 pts  (100 tasks)

  Biggest task-level differences:
    BF-014   +40  (V=35 C=75)
    LC-012   +15  (V=65 C=80)
```

The lift is computed per-task (configured score minus vanilla score), averaged across all tasks, and tested for statistical significance. Capability-level breakdowns show where your workflow configuration actually helps vs. adds overhead.

## CLI Reference

| Command | Description |
|---------|-------------|
| `awb run [tool] [options]` | Run benchmark tasks |
| `awb gap <run_dir>` | Analyze capability gaps and generate improvement suggestions |
| `awb compare <run1> <run2>` | Compare two runs with significance testing |
| `awb export <run_dir> -o file.json` | Export results in external submission format |
| `awb submit <file.json>` | Validate and display an external submission |
| `awb compare-submissions <a.json> <b.json>` | Cross-tool comparison with statistics |
| `awb quickstart` | Verify setup: tools available, tasks load, validation passes |
| `awb info <task_id>` | Show task details |
| `awb tools` | List registered adapters and availability |
| `awb validate` | Validate all task YAMLs against schema |
| `awb leaderboard` | Generate HTML leaderboard from run results (Chart.js radar, CSV export, history tracking) |
| `awb migrate-results <old_dir>` | Convert v0.5.x result JSON files to v1.0 format |
| `awb workflow <subcommand>` | Export, validate, diff, or init workflow descriptors |
| `awb stability <run_dirs>...` | Per-task score stability report |
| `awb calibrate-difficulty <run_dirs>... [--apply]` | Recalibrate difficulty labels from empirical pass rates |
| `awb calibrate-timeouts <run_dirs>... [--apply]` | Tighten timeouts from empirical p95 data |

**Common options for `awb run`:**

```bash
awb run                            # all tools, all tasks, 3 runs
awb run claude-code-custom         # single tool
awb run -t BF-001                  # single task
awb run --category legacy-code     # filter by category
awb run --difficulty hard          # filter by difficulty
awb run --capability bug_diagnosis # filter by capability
awb run --runs 1 --dry-run        # preview without executing
awb run --resume                   # skip tasks with existing results
awb run --parallel -j 4            # run 4 tasks concurrently
awb run --adaptive                 # re-run near-miss tasks (60-99%) after initial pass
```

## Adding Tasks

Tasks live in `awb/tasks/<category>/`. Copy `awb/tasks/_template.yaml`:

```yaml
id: BF-012
category: bug-fix
title: "Fix response_model silently dropping extra fields in FastAPI"
difficulty: easy
estimated_minutes: 15
languages: [python]
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

Run `awb validate` to check your task before opening a PR. Full guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## Supported Tools

| Adapter | Name | Status |
|---------|------|--------|
| Claude Code (vanilla) | `claude-code-vanilla` | Full |
| Claude Code (custom) | `claude-code-custom` | Full |
| Pi | `pi` | Full |
| Gemini CLI | `gemini-cli` | Full |
| Codex CLI | `codex-cli` | Full |
| Cursor | `cursor` | Stub |
| Aider | `aider` | Stub |
| Windsurf | `windsurf` | Stub |
| Copilot | `copilot` | Stub |

Run `awb tools` to see which are available in your environment.

## Adding Tools

Implement the `ToolAdapter` ABC in `awb/adapters/`. v1.0 adds four optional methods to the ABC:

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

    # Optional — implement to enable pre-flight auth checks
    def supports_auth_check(self) -> bool: ...
    def check_auth(self) -> tuple[bool, str]: ...

    # Optional — implement to enable streaming metrics
    def supports_streaming(self) -> bool: ...
    def get_model_pricing(self) -> dict[str, float]: ...
```

Register in `awb/adapters/registry.py` and add an entry point in `pyproject.toml`.

## External Submissions

Anyone can share results using the submission format defined in `results/submission-schema.json`:

```bash
awb run --runs 3
awb export results/runs/<run_dir>/ -o my-results.json
awb submit my-results.json                        # validate locally
awb compare-submissions a.json b.json             # compare with significance testing
```

The format captures tool version, model, hardware class, and per-task run results. Hardware classes (e.g., `apple_m5_24gb`, `linux_x86_16gb`) enable fair speed comparisons — only compared within the same tier.

## Statistical Framework

- Confidence intervals via t-distribution (no scipy required for core scoring)
- Significance testing via sign test for paired tool comparison
- Integrity checks: contamination detection (completions <10s flagged), variance anomalies (identical times/tokens across runs)
- Weight profiles: `default`, `correctness_focused`, `production` (see `awb/scoring/weights.yaml`)
- Stability metric: per-task `TaskStability` (std_dev, score_range, is_unstable); high-variance tasks can be down-weighted in composite scoring

## Links

- [Methodology](METHODOLOGY.md) — Fair comparison principles, metric definitions, known limitations
- [Architecture](ARCHITECTURE.md) — Module graph, data models, pipeline diagrams
- [Contributing](CONTRIBUTING.md) — Adding tasks, tools, and submitting results
- [PyPI](https://pypi.org/project/awb/) — `pip install awb`

## License

MIT
