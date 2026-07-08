<div align="center">
  <h1>AI Workflow Benchmark (AWB)</h1>
  <p><strong>Benchmarks the full AI coding stack (tool, configuration, workflow, model) on 100 real-repo tasks.</strong></p>
  <p>
    <a href="https://pypi.org/project/awb/"><img src="https://img.shields.io/pypi/v/awb" alt="PyPI"></a>
    <a href="https://github.com/xmpuspus/ai-workflow-benchmark/actions"><img src="https://img.shields.io/github/actions/workflow/status/xmpuspus/ai-workflow-benchmark/test.yml" alt="Tests"></a>
    <img src="https://img.shields.io/badge/tasks-100-blue" alt="Tasks">
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
    <a href="https://doi.org/10.5281/zenodo.20361437"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.20361437.svg" alt="DOI"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  </p>
  <br/>
  <img src="demos/hero.gif" alt="awb tools, awb validate, awb gap, awb cost, awb leaderboard --readiness output" width="820"/>
  <br/>
  <sub>v1.5: benchmark your own setup - mine private tasks from your merged PRs, A/B test your CLAUDE.md, catch silent regressions, and price every solved task.</sub>
</div>

---

## Why This Exists

The 2025 Stack Overflow Developer Survey shows 84% of professional developers using AI in their workflow, up from 76% the year before. Yet only 33% trust AI accuracy while 46% actively distrust it ([survey.stackoverflow.co/2025/ai](https://survey.stackoverflow.co/2025/ai)). [METR's RCT of 16 experienced open-source maintainers](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) found AI tooling **increased** task completion time by 19%, while developers self-reported a 20% speedup, a 39-point gap between perception and reality ([arXiv:2507.09089](https://arxiv.org/abs/2507.09089)). Static issue benchmarks like SWE-bench Verified measure model capability in isolation; [SWE-bench Pro](https://scaleapi.github.io/SWE-bench_Pro-os/) ([arXiv:2509.16941](https://arxiv.org/abs/2509.16941)) addresses contamination at scale but still scores patches, not whether a workflow can ship.

AWB measures whether a configured tool+workflow combination can ship correct, regression-safe, low-burden changes against pinned real-world repositories. The same model running vanilla Claude Code vs. a purpose-built setup with a tuned CLAUDE.md, hooks, and structured agents produces meaningfully different results on real engineering tasks. AWB benchmarks the full stack: **tool + configuration + workflow + model**, together, on 100 tasks drawn from real open-source repositories.

### How AWB relates to other benchmarks

Related work measures complementary axes. [HAL](https://arxiv.org/abs/2510.11977) analyzes agent traces with LLM judges across 11 tasks at 2.5B-token scale. [Artificial Analysis](https://artificialanalysis.ai/agents/coding-agents) publishes harness-vs-harness comparisons holding the model constant. [SWE-bench Verified](https://www.swebench.com/) and [SWE-bench Pro](https://scaleapi.github.io/SWE-bench_Pro-os/) score patches against real GitHub issues. [LiveCodeBench](https://arxiv.org/abs/2403.07974) addresses contamination by time-segmenting contest problems. [METR RE-Bench](https://arxiv.org/abs/2411.15114) compares humans and agents in matched ML-engineering environments.

AWB's distinct contribution is twofold: (1) a paired **vanilla-vs-custom** adapter pair that isolates the workflow-configuration delta for the same model, surfaced as a single Workflow Lift score with a sign-test p-value; (2) **deterministic** trace-grading rubrics (read-tests-before-edit, ran-verification-after-change, no-out-of-scope-edits, no-repeated-failing-loop) computed from OpenTelemetry-aligned `.trace.jsonl` artifacts, not LLM judges. See [METHODOLOGY.md#related-work](METHODOLOGY.md#related-work) for citation details.

## What's New in v1.5.4

- **`awb run --dry-run` is instant.** The preview paid the adapter auth preflight, a real model call that can take 30 seconds; a dry run now prints the task table without touching the adapter. Surfaced while recording the from-pr demo below.

- **`awb task from-pr` fetches PR files correctly.** The files call passed per_page as a gh -F field, which silently turns the GET into a POST that GitHub 404s, so mining failed on every real PR. per_page now rides the query string; caught by the live fresh-venv smoke against a real merged PR.
- **`awb submit` accepts the trust columns.** The v1.4.0 baselines added `readiness`, `trace_summary`, and per-run `trace_grade` blocks, but the submission schema still rejected them, so validating an `awb export` (or the published baseline itself) failed. Both schema copies now define the blocks, with a guard test keeping them in sync. `trace_summary: null` (zero graded traces) validates too.

The rest of the 1.5 line - the harness-tuning release: the instrument now points at your own stack, not just the public task set. See [Benchmark Your Own Setup](#benchmark-your-own-setup) for the full loop.

- **`awb task from-pr <pr_url>`** mines a private benchmark task from a merged GitHub PR: pre-merge SHA pinned, the PR's test files overlaid onto the old tree, provenance stamped `real_pr`. Run private sets with **`awb run --tasks-dir`**; the task-set hash now reflects the directory actually loaded.
- **`awb ab --config-a <dir> --config-b <dir>`** answers "did my CLAUDE.md change help?": same adapter, two config dirs, paired sign test, per-arm config hashes recorded.
- **`awb drift`** compares a fresh run against a prior run or published baseline and exits 1 past the threshold, built for cron/CI regression watch.
- **`awb cost`** reports dollars per solved task (failed-attempt spend included), wasted spend, and tokens per solve.
- **`awb gap --prescribe`** turns trace-rubric failures and weak capabilities into ready-to-paste CLAUDE.md snippets with task-level evidence.

Carried over from v1.2.0-v1.4.0: real deterministic trace grading, baselines with trust columns, public GitHub Pages leaderboard, task-set hash on every result, the Production Readiness Score, strict result schema v2, exact-pinned dependencies, and the documented security boundary.

## Quick Start

```bash
pip install awb

awb quickstart                                        # verify your setup
awb warmup                                            # pre-build workspace templates (one-time, ~5 min)
awb run --fast-check claude-code-custom               # 8 tasks, ~15 min, ~$4 (quick signal)
awb run --progressive --adaptive claude-code-custom   # full suite with early exit + smart re-runs
awb gap results/runs/<run_dir>/                       # analyze capability gaps
awb leaderboard --readiness --explain                 # Production Readiness Score per tool
```

### Five-minute reproducible demo

Run this end-to-end against the published v1.4.0 fast-check baseline. Should finish in ~15 minutes for ~$4 of API spend and produce a tweetable Workflow Lift number plus a capability profile.

```bash
pip install awb==1.5.4
awb quickstart                                       # 1. verify environment
awb warmup --use-uv                                  # 2. pre-build templates
awb run --fast-check claude-code-custom              # 3. ~15 min, ~$4, real run
awb leaderboard --readiness --explain                # 4. composite readiness score
awb trace grade results/runs/<run_id>/               # 5. behavior rubric scores
```

Compare against the published baseline at `results/baselines/claude-code-custom-1.4.0-fast-check.json`. Same `task_set_hash` means your numbers are directly comparable.

**New in v1.1.0:** `awb warmup` caches workspaces for 10-30x faster setup. `--fast-check` gives a quick signal in 15 min for ~$4. `--progressive` stops early on weak tools. `--use-uv` swaps pip for uv. See [Execution Modes](#execution-modes) below.

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

> **Security:** AWB clones third-party repos and runs their setup/test code plus the AI tool with no sandbox. Treat task sets and their repos as trusted input and run in a disposable environment. See [docs/SECURITY.md](docs/SECURITY.md) for the trust boundary and the planned per-task Docker isolation.

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
| Efficiency | 2% | Blend of iteration count and tokens-per-iteration |

**Weight profiles** (select with `load_weight_profile(name)`):

| Profile | Focus | Use When |
|---------|-------|----------|
| `default` | Balanced | Standard evaluation |
| `correctness_focused` | 70% correctness | Research-grade rigor |
| `production` | 45% correctness, 20% cost, 10% reliability, 8% security | Shipping to users |
| `token_efficient` | 25% cost, 15% efficiency | Tight API budgets |
| `rate_limited` | 30% cost, 15% efficiency | Hitting TPM/RPM limits |

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

Real open-source repos, pinned to release tag SHAs. Setup runs in under 15 seconds via venv + pip.

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

**Repos used:** FastAPI (74), httpx (17), Flask (4), Click (4), Starlette (1). All Python.

**Task IDs:**
`BF-001–014` · `FA-001–010` · `RF-001–012` · `CR-001–010` · `DB-001–011` · `MF-001–009` · `LC-001–012` · `WF-001–030`

## Capability Profiles

Each task maps to 1–3 capabilities, producing a radar chart of tool strengths:

| Capability | Tasks | What It Measures |
|------------|-------|-----------------|
| code_comprehension | 45 | Understanding existing code before modifying |
| framework_knowledge | 36 | Knowing API patterns (Pydantic v2, async SQLAlchemy, etc.) |
| refactoring_discipline | 29 | Changing code without breaking behavior |
| bug_diagnosis | 27 | Structured root cause analysis, test-first diagnosis |
| multi_file_reasoning | 22 | Coordinating changes across multiple files |
| test_writing | 12 | Writing correct, meaningful tests |
| security_awareness | 10 | Identifying and fixing vulnerabilities |
| convention_adherence | 8 | Discovering and following project conventions |
| context_discovery | 5 | Reading project docs and config before editing |
| security_methodology | 5 | Applying security checklists systematically |
| completeness_tracking | 4 | Following all requirements, not stopping at 80% |
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

When `awb run` executes both vanilla and custom (the default), it produces a **Workflow Lift**, a single number measuring how much your workflow configuration improves over the baseline:

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

## Benchmark Your Own Setup

The 100 public tasks calibrate the instrument. The point of the instrument is your own stack: your repos, your CLAUDE.md, your hooks. Four commands (new in v1.5) close that loop:

```bash
# 1. Mine private tasks from your own merged PRs. No contamination:
#    nobody trained on your repo's future.
awb task from-pr https://github.com/you/repo/pull/123 --out ./tasks

# 2. Run them.
awb run claude-code-custom --tasks-dir ./tasks

# 3. Changed your CLAUDE.md? Measure it: same adapter, two config dirs,
#    paired sign test.
awb ab claude-code-custom --config-a ~/.claude --config-b ./candidate-config

# 4. Turn failures into config fixes: rubric failures and weak capabilities
#    become ready-to-paste CLAUDE.md snippets.
awb gap results/runs/<run_dir>/ --prescribe

# 5. Watch for silent regressions (models and harnesses update weekly).
#    Exit code 1 on drift, so it slots straight into cron or CI.
#    Point it at a single run directory (one _runN dir per benchmark pass).
awb drift results/runs/<run_id>_run1/ --baseline results/baselines/<ref>.json

# 6. Know what a correct change costs before you standardize on a config.
awb cost results/runs/<run_dir>/
```

The loop, recorded live against a real merged PR ([xmpuspus/cloudwright#69](https://github.com/xmpuspus/cloudwright/pull/69), a production bug fix with its own regression test):

![awb task from-pr mining a real merged PR, validating it, and loading it with awb run --tasks-dir](demos/from-pr.gif)

`from-pr` pins the pre-merge commit, overlays the PR's test files onto the old tree (tests exist, implementation does not), and writes a schema-valid task YAML with provenance stamped `real_pr`. Two caveats. First, the test-file overlay resolves objects through AWB's local mirror cache, then falls back to fetching from GitHub; if both miss, refresh the mirror with `awb warmup --clear`. Second, a mined task executes the PR's own test and setup code on your machine during benchmark runs, so only mine repos you trust (see [docs/SECURITY.md](docs/SECURITY.md)).

## CLI Reference

### `awb run` - Run benchmark tasks

```bash
awb run                            # all tools, all tasks, 3 runs (vanilla vs custom comparison)
awb run claude-code-custom         # single tool
awb run -t BF-001                  # single task
awb run --category legacy-code     # filter by category
awb run --difficulty hard          # filter by difficulty
awb run --capability bug_diagnosis # filter by capability
awb run --runs 1 --dry-run        # preview without executing
awb run --resume                   # skip tasks with existing results
awb run --parallel -j 4            # run 4 tasks concurrently
awb run --adaptive                 # re-run near-miss tasks (60-99%) after initial pass
awb run --progressive              # easy → medium → hard, stop early if pass rate too low
awb run --fast-check               # 8 representative tasks, 1 run (~15 min, ~$4)
awb run --use-uv                   # use uv instead of pip for 10-30x faster installs
```

### Execution Modes

AWB v1.1 ships four execution modes tuned for different evaluation scenarios:

| Mode | Tasks run | Wall clock | Token cost | Use when |
|------|-----------|-----------|-----------|----------|
| Full suite | 300 (100 × 3 runs) | ~3 hrs | ~$150 | Final evaluation, publishing results |
| Full + adaptive | ~180 | ~1.5 hrs | ~$100 | Standard workflow, strong tools |
| Progressive | ~150 on weak tools | ~1 hr | ~$40-75 | Unknown/mediocre tools |
| Fast-check | 8 | ~15 min | ~$4 | PR gates, iterating on config |

**Fast-check** (8 representative tasks, 1 per category, reports estimated full-suite score ± margin):

**Progressive** (easy → medium → hard, stops if easy pass rate < 40% or medium < 20%):

**`--use-uv`** (rewrites `pip install` → `uv pip install` for 10-30x faster installs):

### `awb warmup` - Pre-build workspace templates

```bash
awb warmup              # build templates for all 63 unique (repo, commit, setup) combos
awb warmup --dry-run    # show combos without building
awb warmup --clear      # reset template cache
awb warmup --use-uv     # use uv for faster initial builds
```

Workspace templates are cached at `~/.cache/awb/templates/`. First build takes ~5 min; subsequent `awb run` invocations copy templates in ~2s instead of running `pip install` from scratch. Cuts ~55 min off a full benchmark run with 74 FastAPI tasks.

### `awb gap` - Capability gap analysis

Analyzes results to produce a capability radar, failure classification, systematic patterns, and ranked improvement suggestions. Add `--prescribe` to turn trace-rubric failures and weak capabilities into concrete prescriptions: each one names the trigger (for example `trace:no_out_of_scope_edits`), the tasks it fired on, and a ready-to-paste CLAUDE.md snippet.

### `awb task from-pr` - Mine a private task from a merged PR

```bash
awb task from-pr <pr_url> --out ./tasks [--category bug-fix] [--difficulty medium] \
  [--test-command "python -m pytest"] [--dry-run]
```

Fetches the PR via the `gh` CLI, pins the pre-merge SHA, splits changed files into tests vs source, and generates a task YAML whose setup overlays the PR's test files onto the pre-merge tree. The generated file is validated against the schema (partial credit sums to 100) before it is written. Run private tasks with `awb run --tasks-dir ./tasks`.

### `awb ab` - Paired config A/B test

```bash
awb ab claude-code-custom --config-a <dir> --config-b <dir> [--task BF-001] [--category bug-fix]
```

Runs the same adapter over the same tasks twice, once per config dir (via `CLAUDE_CONFIG_DIR` for Claude Code), then reports per-task deltas, mean lift, and a binomial sign-test p-value. Both config hashes are printed for reproducibility.

### `awb drift` - Alert on regression against a baseline

```bash
awb drift results/runs/<run_id>_run1/ --baseline <run_dir_or_baseline.json> --threshold 5.0
```

Compares mean score and per-task scores against a reference (a prior single run directory such as `<run_id>_run1/`, or a published awb/v2 baseline JSON). Exits 1 when the mean drops more than the threshold, 0 otherwise, so a cron job or CI step can alert on silent model or harness regressions. Warns when task-set hashes differ.

### `awb cost` - Cost per solved task

```bash
awb cost results/runs/<run_dir>/ [<more_run_dirs>...]
```

Groups results by tool and reports the procurement numbers: total spend, spend per solved task (total spend divided by solves, so failed attempts count), wasted spend on failures, and tokens per solve.

### `awb compare` - Compare two runs

Side-by-side comparison of two benchmark runs with significance testing.

### `awb tools` - List adapters

Shows all registered tool adapters and their availability status.

### `awb validate` - Validate task YAMLs

Checks all 100 task YAML files against the schema, including partial credit sum-to-100 validation.

### `awb info` - Task details

Displays full details for a specific task including repo, capabilities, and partial credit rubric.

### `awb stability` - Score stability report

Per-task score variance across multiple runs. Flags unstable tasks for prompt clarification or tighter verification.

### `awb leaderboard` - Generate HTML leaderboard

Generates a static HTML site with Chart.js radar chart, CSV export, and historical run tracking.

Add `--readiness` to print the **Production Readiness Score** per tool to stdout. The score is a weighted composite of correctness (35%), regression-safety (20%), security (15%), review-burden (10%), maintainability (8%), cost (7%), and speed (5%), all normalized 0-100. Weighted for shipping safety rather than headline accuracy.

### `awb trace grade` - Score behaviors from trace artifacts

Every benchmark run writes a `<task_id>_<tool>.trace.jsonl` file using OpenTelemetry GenAI semantic conventions (`gen_ai.client.operation`, `gen_ai.tool.use`, `gen_ai.usage.input_tokens`) plus AWB-specific spans for shell commands (`task.shell_command`), file edits (`task.file_edit`), and test runs (`task.test_run`). `awb trace grade <run_dir>` reads each trace and scores four shipping disciplines on a 0-100 scale:

| Behavior | What it checks |
|----------|----------------|
| `read_tests_before_edit` | Did the tool read a test file before its first edit? |
| `ran_verification_after_change` | Was a test run / pytest invocation issued after the last file edit? |
| `no_out_of_scope_edits` | Did edits stay within `files_to_examine` from the task spec? |
| `no_repeated_failing_command_loop` | Did the tool retry the same failing shell command 2+ times? |

### `awb calibrate-difficulty` - Recalibrate difficulty labels

Recalibrates task difficulty labels from empirical pass rates. Use `--apply` to write changes back to task YAMLs.

### `awb calibrate-timeouts` - Tighten timeouts

Recomputes task timeouts from empirical p95 wall-clock data. Use `--apply` to write changes.

### Other commands

| Command | Description | Demo |
|---------|-------------|------|
| `awb quickstart` | Verify setup: tools available, tasks load | - |
| `awb export <run_dir> -o file.json` | Export results in submission format | - |
| `awb submit <file.json>` | Validate an external submission | - |
| `awb compare-submissions <a> <b>` | Cross-tool comparison with statistics | - |
| `awb migrate-results <old_dir>` | Convert v0.5.x results to v1.0 format | - |
| `awb workflow <subcommand>` | Export, validate, diff, or init descriptors | - |
| `awb --version` | Show version | - |
| `awb run --dry-run` | Preview tasks without executing | - |

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
| Cursor | `cursor` | Planned |
| Aider | `aider` | Planned |
| Windsurf | `windsurf` | Planned |
| Copilot | `copilot` | Planned |

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
                      max_turns: int = 20, timeout_seconds: int = 1800,
                      on_event=None) -> ToolResult:
        ...  # on_event(event) callback for streaming token monitor; return False to abort

    def check_available(self) -> bool:
        ...

    def get_config_hash(self) -> str:
        ...

    # Optional - implement to enable pre-flight auth checks
    def supports_auth_check(self) -> bool: ...
    def check_auth(self) -> tuple[bool, str]: ...

    # Optional - implement to enable streaming metrics
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

The format captures tool version, model, hardware class, and per-task run results. Hardware classes (e.g., `apple_m5_24gb`, `linux_x86_16gb`) enable fair speed comparisons: speeds are only compared within the same tier.

## Statistical Framework

- Confidence intervals via t-distribution (no scipy required for core scoring)
- Significance testing via sign test for paired tool comparison
- Integrity checks: contamination detection (completions <10s flagged), variance anomalies (identical times/tokens across runs)
- Weight profiles: `default`, `correctness_focused`, `production`, `token_efficient`, `rate_limited` (see `awb/scoring/weights.yaml`)
- Stability metric: per-task `TaskStability` (std_dev, score_range, is_unstable); high-variance tasks can be down-weighted in composite scoring
- Token efficiency: sigmoid normalizer (optimal=2k tokens/iter, baseline=15k) blended 50/50 with iteration count in the efficiency dimension

## Changelog

### 1.5.4 (2026-07-08)

`awb run --dry-run` no longer pays the adapter auth preflight (a live model call); previews print instantly. Adds the from-pr demo GIF recorded against a real merged PR.

### 1.5.3 (2026-07-08)

`awb task from-pr` files fetch fixed: gh api -F fields switch GET to POST and GitHub 404s the files endpoint; per_page moved into the query string. Found by running the published wheel against a real merged PR.

### 1.5.2 (2026-07-08)

Submission schema also accepts trace_summary: null, which exports write when zero traces were graded. Caught by the same fresh-venv smoke that caught 1.5.1's gap.

### 1.5.1 (2026-07-08)

Submission schema accepts the v1.4.0 trust columns (readiness, trace_summary, per-run trace_grade); packaged and repo schema copies pinned in sync by a regression test. Caught by the v1.5.0 fresh-venv release smoke.

### 1.5.0 (2026-07-08)

Harness tuning: `awb task from-pr` + `awb run --tasks-dir` (private tasks from merged PRs), `awb ab` (paired config A/B via CLAUDE_CONFIG_DIR), `awb drift` (baseline regression alerts with an exit-code contract), `awb cost` (cost per solved task), `awb gap --prescribe` (config prescriptions from rubric failures). Task-set hash now derives from the loaded tasks directory; `--resume` with `--tasks-dir` is refused to prevent cross-set contamination; Rich markup disabled on all prints carrying PR-derived text.

### 1.4.0 (2026-05-30)

Real trace grading (tool_use blocks translated to FILE_EDIT/SHELL_COMMAND spans; span-less traces report null, never a fake 100), baselines with per-run trace_grade and readiness columns, `-j N` enables parallel mode on its own, Aider became a real adapter, exact-pinned runtime dependencies with freshness guard tests, security posture documented in docs/SECURITY.md.

### 1.1.0 (2026-04-07)

Performance and token optimization release. 33-50% faster full runs, ~97% cheaper quick evaluations.

- **Workspace template cache** - ~55 min saved on full runs (74 FastAPI tasks no longer re-run pip install)
- **`awb warmup`** - pre-build all unique workspace templates in parallel
- **`--use-uv`** - 10-30x faster pip installs via uv
- **`--progressive`** - easy → medium → hard execution, stops early if weak tool (50-80% token savings)
- **`--fast-check`** - 8 representative tasks, 1 run, ~15 min, ~$4 (97% cheaper than full suite)
- **Token budget enforcement** - `max_input_tokens`/`max_output_tokens` in task constraints, streaming kill switch
- **Streaming token monitor** - Claude Code adapter parses stream events as they arrive
- **Parallel partial credit** - independent grep/file checks run via asyncio.gather; pytest stays sequential
- **Adaptive timeouts** - runs 2+ tighten timeout to `min(original, 2x run1_actual)`
- **Richer RunCost** - cache_read, cache_creation, thinking token fields
- **Token efficiency in scoring** - efficiency dimension blends iterations + tokens-per-iteration
- **Two new weight profiles** - `token_efficient` and `rate_limited` for cost-sensitive evaluation
- **Token-aware gap analysis** - cost-per-point outliers, cache hit rate patterns, token burn detection
- **JSONL results** - additive output format alongside per-file JSON for fast batch loading
- **184 tests** (up from 135)

### 1.0.9 (2026-04-04)

- Add Python 3.13 and 3.14 to CI test matrix and PyPI classifiers

### 1.0.8 (2026-04-04)

- Sync README changelog with PyPI long description; update GitHub repo description (80 → 100 tasks)

### 1.0.7 (2026-04-04)

Product audit fixes: 27 findings across observability, scoring, reliability, performance, and CLI safety.

- **Observability:** `--verbose` flag, test output logging, captured partial credit output, specific exception handlers, integrity checks in `awb run`
- **Scoring:** `SECURITY_METHODOLOGY` capability, signed lint delta, removed hardcoded `METRIC_WEIGHTS`, timeout calibrator can increase, leaderboard uses per-task aggregate scoring
- **Reliability:** `KeyboardInterrupt` handling, `load_single` None guard, `find_incomplete_run` scans all `_runN` dirs, 600s setup timeout, `return_exceptions` in gather, finally cleanup
- **Performance:** bare-clone cache (`~/.cache/awb/clones/`), cached `RunEnvironment`/adapter, schema cache
- **CLI safety:** confirmation prompt (`--yes`), `quickstart` is env-only check, resolved paths, `check_available` guard for stubs

### 1.0.6 (2026-04-03)

- Add trustme to 4 real httpx repo tasks (BF-003, BF-011, BF-013, FA-005)

### 1.0.5 (2026-04-02)

- Add trio to 16 httpx-based tasks (fixes silent pytest crash on Python 3.13+)

### 1.0.4 (2026-04-01)

- Fix 4 verification bugs (FA-010, RF-012, CR-007, BF-003)

<details>
<summary>Older releases</summary>

See [CHANGELOG.md](CHANGELOG.md) for the full history (v1.0.0, v0.5.x, v0.4.x, v0.3.x, v0.2.x, v0.1.0).

</details>

## Links

- [Methodology](METHODOLOGY.md) - Fair comparison principles, metric definitions, related work, known limitations
- [Architecture](ARCHITECTURE.md) - Module graph, data models, pipeline diagrams
- [Contributing](CONTRIBUTING.md) - Adding tasks, tools, and submitting results
- [PyPI](https://pypi.org/project/awb/) - `pip install awb`

## Citing AWB

If you use AWB in research, cite it via Zenodo. The concept DOI [`10.5281/zenodo.20361437`](https://doi.org/10.5281/zenodo.20361437) always resolves to the latest release; each release also mints a version-specific DOI listed on the Zenodo record. Machine-readable metadata lives in [CITATION.cff](CITATION.cff) and [codemeta.json](codemeta.json); release process is in [docs/zenodo-doi.md](docs/zenodo-doi.md).

```bibtex
@software{puspus_awb_2026,
  author    = {Puspus, Xavier},
  title     = {{AWB: AI Workflow Benchmark}},
  version   = {1.5.4},
  year      = {2026},
  month     = may,
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.20361437},
  url       = {https://doi.org/10.5281/zenodo.20361437}
}
```

## License

MIT
