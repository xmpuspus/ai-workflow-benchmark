# AWB Fair Comparison Methodology

## Scope

AWB benchmarks the tool+workflow, not models in isolation. The same underlying model running in a bare CLI invocation vs. a purpose-built workflow with hooks, agents, and structured prompts will produce meaningfully different results on real engineering tasks. AWB captures that difference.

Model-only benchmarks (SWE-bench, Aider Polyglot, HumanEval) are complementary - they measure raw capability. AWB measures how much of that capability a tool+workflow actually delivers in practice.

## Fair Comparison Principles

### 1. Same prompt

Every tool receives an identical task description string. No adapter gets additional context, hints, or instructions beyond what the task YAML defines. The prompt is templated from `issue.description` plus a standard header specifying the goal and success criteria.

### 2. Same starting state

Each run starts from a fresh `git clone` at the exact pinned commit SHA recorded in the task definition. Setup commands (dependency installation, database migrations) run identically for every tool. No run inherits state from a previous run.

### 3. Same timeout

Every tool receives the same `timeout_seconds` limit defined in the task. Runs that exceed the timeout are recorded as failures with exit code 124.

### 4. Same verification

All tools are evaluated by the same test suite, lint commands, and partial credit rubric. Verification runs in a clean subprocess after the tool finishes. No tool gets special scoring logic.

### 5. Tool-native features allowed

Each tool is permitted to use its full native feature set:

- Claude Code: CLAUDE.md, hooks, custom agents, slash commands
- Cursor: rules files, composer agents
- Aider: architect mode, editor model separation
- IDE integrations: autocomplete, inline diff, language server features

The benchmark measures what the tool delivers with its best configuration. A vanilla baseline (no custom config) is always included alongside the configured variant so the workflow contribution can be isolated.

### 6. Three runs minimum

Each task-tool combination runs at least 3 times. Results report the median to reduce variance from non-determinism in LLM outputs and execution environment. Outlier runs (>2 standard deviations from the median) are flagged in the results.

### 7. Version pinning

Every result record includes:

- `tool_version` - CLI or API version of the tool
- `model` - exact model identifier (e.g., `claude-opus-4-6`)
- `run_id` - includes the date to group runs chronologically
- Repo commit SHA from the task definition

Results are not aggregated across different tool versions or model versions.

### 8. Open methodology

All benchmark code, task definitions, prompts, scoring logic, and raw results are published in this repository. Anyone can reproduce a run by following the Quick Start guide and pinning the same versions.

### 9. Known limitations stated explicitly

See the Known Limitations section below.

## Metrics

### Correctness (weight: 55%)

Combined from two sub-metrics:

- **Success rate (60% of correctness)**: Binary pass/fail determined by `verification.test_commands`. All commands must exit 0 for success.
- **Partial credit (40% of correctness)**: Rubric-based score from 0 to `partial_credit_max`. Each criterion is a shell command that exits 0 (pass) or non-zero (fail). Captures graduated competence when full success isn't reached.

### Cost efficiency (weight: 15%)

Estimated USD per task based on token counts. Normalized using sigmoid curve with per-task baselines derived from difficulty:

| Difficulty | Optimal (~95 score) | Baseline (~50 score) |
|------------|--------------------|--------------------|
| Easy | $0.05 | $0.30 |
| Medium | $0.20 | $1.00 |
| Hard | $1.00 | $3.00 |

### Speed (weight: 10%)

Wall-clock seconds from process start to exit. Baseline derived from task's `estimated_minutes`: optimal = 50% of estimate, baseline = 100% of estimate.

### Code quality (weight: 10%)

Delta in lint warning count between pre-run and post-run states. Optimal = 0 delta, baseline = 5 new warnings per task.

### Reliability (weight: 5%)

Count of pre-existing passing tests broken by changes. Optimal = 0 regressions, baseline = 2 regressions per task.

### Security (weight: 3%)

Delta in security findings from `verification.security_commands`. Optimal = 0 new issues, baseline = 3 new issues per task.

### Efficiency (weight: 2%)

A 50/50 blend of two sigmoid-normalized sub-scores:

- **Iteration count** — tool turns used versus per-task baselines (easy optimal=3, medium=8, hard=15; baseline = `constraints.max_iterations`)
- **Tokens per iteration** — total tokens divided by iteration count, normalized against optimal=2,000 and baseline=15,000

This dual measurement distinguishes between two failure modes that raw iteration count cannot separate: a tool that finishes in 3 turns by reading half the codebase (low iters, high tokens/iter) and a tool that finishes in 8 focused turns (higher iters, low tokens/iter). The latter is more token-efficient even though it used more iterations, and scores higher on this dimension.

### Token budget enforcement

Tasks can specify `constraints.max_input_tokens` and `constraints.max_output_tokens` (both default to 0 = unlimited). When set, the Claude Code adapter streams stream-json events in real time and calls a budget-check callback on every event. If the running input or output token total exceeds the budget, the callback returns `False`, the adapter terminates the subprocess gracefully (SIGTERM → wait 5s → SIGKILL), and the task is scored on whatever partial credit was earned up to that point. This prevents runaway consumption on tasks where a tool enters a context-read loop, and makes rate-limited evaluation scenarios directly measurable.

## Task Design

### Source selection

Tasks are drawn from real open-source repositories at pinned commits. Synthetic or toy tasks are excluded. Each task must:

- Have a verifiable ground truth (passing tests, correct lint output)
- Be completable within 30-45 minutes by a skilled developer
- Exercise the task category meaningfully (no trivial one-line fixes for "multi-file")

### Categories and distribution

| Category | Count | Rationale |
|----------|-------|-----------|
| bug-fix | 12 | Most common real-world task; includes test-first diagnosis and performance bugs |
| feature-addition | 9 | Extension points, ambiguous requirements, infrastructure, documentation |
| refactoring | 11 | Semantic preservation, performance optimization, CI/CD config |
| code-review | 9 | Security review (report-only), concurrency analysis, migration guides |
| debugging | 10 | Hypothesis generation, regression bisection, profiling, stack traces |
| multi-file | 7 | Cross-module reasoning, merge conflicts, dependency migration |
| legacy-code | 12 | Modernization, large codebase navigation, deprecation patterns |
| workflow | 30 | TODO completeness, hook/skill integration, configuration tasks |

### Difficulty levels

- **easy** (48 tasks) - Single file, under 50 lines changed, obvious fix (empirical pass rate >65%)
- **medium** (17 tasks) - 1-3 files, moderate reasoning required (empirical pass rate 35-65%)
- **hard** (35 tasks) - Multiple files, non-obvious root cause, architectural decisions (empirical pass rate <35%)

Difficulty labels are calibrated from empirical pass rates collected across benchmark runs. The `awb calibrate-difficulty` command recalibrates labels when sufficient run data exists; `--apply` writes the updated labels back to task YAMLs.

### Capability mapping

Each task maps to 1-3 capabilities from a fixed taxonomy. This enables capability radar charts showing tool strengths and weaknesses:

| Capability | Tasks | What it measures |
|------------|-------|-----------------|
| code_comprehension | 45 | Understanding existing code before modifying |
| framework_knowledge | 36 | Knowing API patterns (Pydantic v2, async SQLAlchemy, etc.) |
| refactoring_discipline | 29 | Changing code without breaking behavior |
| bug_diagnosis | 27 | Structured root cause analysis, test-first diagnosis |
| multi_file_reasoning | 22 | Coordinating changes across multiple files |
| test_writing | 12 | Writing correct, meaningful tests |
| security_awareness | 10 | Identifying and fixing security vulnerabilities |
| convention_adherence | 8 | Discovering and following project conventions |
| context_discovery | 5 | Reading project docs and config before editing |
| security_methodology | 5 | Applying security checklists systematically |
| completeness_tracking | 4 | Following all requirements, not stopping at 80% |
| cost_discipline | derived | Token efficiency across all tasks |

### Language distribution

All 100 tasks are Python-based against modern frameworks (FastAPI, httpx, Flask, Click, Starlette) with venv-based setup. Eight tasks also touch Docker, YAML, or Markdown alongside Python.

## Scoring

### Sigmoid normalization

All metrics use a sigmoid curve that maps raw values to [0, 100]:

```
score = 100 / (1 + exp(k * (value - baseline)))
```

Where `k = ln(19) / |baseline - optimal|`. This produces:
- Score ~95 at the optimal value
- Score ~50 at the baseline value
- Smooth decay beyond baseline (never negative, never above 100)

This replaces the v1 linear normalization which collapsed to 0 above the baseline, destroying gradient for expensive or slow but otherwise correct solutions.

### Difficulty-weighted aggregation

Aggregate scores weight by difficulty: easy=1.0, medium=1.5, hard=2.5. A tool that solves hard tasks scores higher than one that only solves easy tasks, even if the easy-task count is higher.

### Stability weighting

High-variance tasks (where scores differ significantly across runs) can optionally be down-weighted in the composite score. The `TaskStability` dataclass tracks `std_dev`, `score_range`, and an `is_unstable` flag per task. When stability weighting is enabled, unstable tasks receive a reduced weight contribution so that noisy measurements don't dominate the aggregate. This is an optional parameter to the composite scoring function and is off by default.

Task-level stability is reported by `awb stability <run_dirs>...`, which reads multiple run directories and produces a per-task breakdown. Tasks with high variance are candidates for prompt clarification or tighter verification criteria.

### Timeout calibration

Task timeouts are calibrated from empirical p95 wall-clock times (p95 × 2.5). Previously, timeouts were set at blanket 900–1800s values. The `awb calibrate-timeouts` command recomputes tighter timeouts from run data; `--apply` writes them back to task YAMLs.

### Weight profiles

Five built-in profiles in `awb/scoring/weights.yaml`:

```yaml
default:
  correctness: 0.55
  cost_efficiency: 0.15
  speed: 0.10
  code_quality: 0.10
  reliability: 0.05
  security: 0.03
  efficiency: 0.02

correctness_focused:  # research-grade: favor getting the right answer above all
  correctness: 0.70
  cost_efficiency: 0.10
  ...

production:  # shipping to users: reliability and security matter more
  correctness: 0.45
  cost_efficiency: 0.20
  reliability: 0.10
  security: 0.08
  ...

token_efficient:  # tight API budgets: cost and per-iteration discipline rewarded
  correctness: 0.40
  cost_efficiency: 0.25
  efficiency: 0.15
  ...

rate_limited:  # hitting TPM/RPM ceilings: cost dominates
  correctness: 0.35
  cost_efficiency: 0.30
  efficiency: 0.15
  ...
```

The `token_efficient` and `rate_limited` profiles exist because the real-world bottleneck for teams using Claude Code has shifted from "does it work" to "does it work within my API budget". A tool that solves 80% of tasks at $0.10 each beats one that solves 85% at $1.00 each when the operator is hitting rate limits. These profiles let users score the same raw results under different economic constraints without re-running.

### Statistical framework

- **Confidence intervals**: t-distribution based (no scipy required). Reports mean, 95% CI lower/upper, standard deviation, and sufficiency flag.
- **Significance testing**: Sign test for paired comparison of two tools on shared tasks. Reports p-value, Cohen's d effect size, and interpretation.
- **Integrity checks**: Contamination detection (completions <10s with success), variance anomalies (identical times/tokens across runs suggesting cached replay).

## Execution Modes

v1.1 introduces three execution modes that trade coverage for speed and token cost. They do not change how scoring works — they change which tasks are run. A result produced in progressive or fast-check mode is scored by the same sigmoid normalization as a full-suite result; the difference is sample size.

**Full mode** (default) runs every task for `--runs` iterations. This is the reference evaluation. Results from this mode are directly comparable across tools.

**Progressive mode** (`--progressive`) sorts tasks by difficulty and runs easy tasks first. After easy tasks complete on run 1, the runner checks pass rate: if below 40%, the run terminates with a clear explanation that the tool is not ready for harder tasks. Same check after medium tasks at a 20% threshold. Progressive results are scored normally but cover only the difficulty tiers that completed — gap analysis will flag that hard tasks were skipped. This mode exists to stop wasting tokens on tools that clearly aren't going to handle non-trivial work.

**Fast-check mode** (`--fast-check`) runs 8 hand-picked representative tasks (one per category) for a single run. It reports an estimated full-suite score with a 95% confidence margin computed from the 8 samples. Fast-check results are not published on the leaderboard — they are a sighting shot. Use them for PR gates, config iteration, or deciding whether a new tool is worth a full evaluation.

**Adaptive runs** (`--adaptive`) is not a mode but a modifier. It applies to runs 2 and 3, skipping tasks that were decisive on run 1 (scored 0%, 100%, or below a configurable minimum) and only re-running near-misses. Combined with adaptive timeout tightening (runs 2+ get `min(original, 2 × run1_actual)` per task), this cuts runs 2-3 wall clock by 40-60% without losing the variance signal that matters.

| Mode | Tasks | Runs | Typical wall clock | Typical API cost |
|------|-------|------|-------------------|------------------|
| Full | 100 | 3 | ~3 hours | ~$150 |
| Full + adaptive | 100 + ~40 | 1 + 2 partial | ~1.5 hours | ~$100 |
| Progressive (strong tool) | 100 | 3 | ~3 hours | ~$150 |
| Progressive (weak tool) | ~48 | 3 | ~1 hour | ~$40-75 |
| Fast-check | 8 | 1 | ~15 minutes | ~$4 |

Wall-clock estimates assume `-j 4` parallelism and the workspace template cache is warm (`awb warmup` run once). Cost estimates are for Claude Opus 4.6 with typical extended thinking.

## Workflow Lift Score

The primary benchmark output when comparing a configured tool against its vanilla baseline. Computed as the mean per-task score difference (configured minus vanilla) across all tasks, with statistical significance testing.

The lift is broken down by capability dimension, showing where the workflow's configuration (CLAUDE.md patterns, hooks, agents, custom settings) actually helps vs adds overhead. This is a direct measurement of workflow contribution — not two independent scores to eyeball, but one number with a p-value.

The vanilla adapter runs the tool with no custom configuration. The custom adapter runs with the user's full setup. Any hooks, automation, or context the user has configured will fire on custom runs but not vanilla. The difference between the two IS the workflow's contribution.

## Gap Analysis

After scoring, `awb gap` produces:

1. **Capability radar** - per-capability scores with confidence based on sample size
2. **Failure classification** - each failure categorized as timeout, test_error, partial_completion, or code_error
3. **Systematic patterns** - cross-task weakness detection (e.g., "fails all multi_file_reasoning tasks")
4. **Improvement suggestions** - rule-based, deterministic recommendations mapped to failure patterns
5. **Ranked actions** - top 5 suggestions ordered by estimated impact

## External Submissions

The `results/submission-schema.json` defines a JSON format for external results:

- Tool name, version, and configuration description
- Model name, provider, and pricing tier
- Hardware class (for fair speed comparison within tiers)
- Per-task results with multiple runs

External submissions can be compared with `awb compare-submissions`, which finds the common task subset, runs significance testing, and reports effect sizes.

## Result Format Versioning (v1.0)

As of v1.0.0, all result JSON files include a `"version": "1.0"` field. Metric keys are aligned with `weights.yaml` dimension names (correctness, cost_efficiency, speed, code_quality, reliability, security, efficiency). Weight profiles are validated to sum to 1.0 on load. Partial credit criteria are validated to sum to exactly 100 points by `awb validate`.

Results from v0.5.x can be converted with `awb migrate-results <old_dir> --output <new_dir>`. The migration adds version fields, renames metrics, and preserves the original data in a `_v05x_original` key for auditability.

**v1.1 additive fields.** Result JSON files now include three new `cost` fields when the tool's stream-json exposes them: `cache_read_tokens`, `cache_creation_tokens`, and `thinking_tokens`. These default to 0 for adapters that don't report them and are backward compatible — any v1.0 loader that reads the `cost` object will simply ignore the new keys. The `constraints` object on task YAMLs adds optional `max_input_tokens` and `max_output_tokens` fields with default 0 (unlimited), so existing task definitions remain valid.

**JSONL output.** Alongside per-file JSON, each benchmark run now appends every result to `{results_dir}/{base_run_id}.jsonl` for fast batch loading. The per-file JSONs remain the source of truth and are unchanged — the JSONL is a projection for tooling that wants to stream results without globbing hundreds of files.

## Known Limitations

**Headless mode does not capture IDE UX.** Autocomplete suggestions, inline diff previews, and visual context provided by IDE integrations are not measurable in a headless subprocess.

**Code review tasks may favor terminal tools.** Review tasks are presented as text prompts. Tools with visual diff integrations lose that advantage.

**Cost depends on model pricing.** Token costs change as providers update pricing. Cost comparisons are valid only within a benchmark run using the same model at the same pricing.

**Hardware affects speed metric.** Wall-clock time varies with CPU speed, memory, and disk I/O. Speed comparisons are valid only within the same hardware class. Hardware is recorded in every result.

**Single-run results are noisy.** Minimum 3 runs recommended. The statistical framework reports confidence intervals and flags insufficient sample sizes.

**Task contamination is possible.** Models may have seen task repo code in training data. Integrity checks flag suspiciously fast completions but cannot guarantee novelty.

## Reproducibility

To reproduce a specific result:

1. Check out this repository at the commit SHA recorded in `run_id`
2. Install the exact tool version from `tool_version`
3. Use the model identifier from `model`
4. Clone the task repo at the commit SHA in the task YAML
5. Run with the same hardware class (noted in `environment.hardware`)
6. Verify configuration via `config_hash` in the result file
