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

Number of tool turns used. Baselines derived from difficulty: easy optimal=3, medium=8, hard=15. Maximum from `constraints.max_iterations`.

## Task Design

### Source selection

Tasks are drawn from real open-source repositories at pinned commits. Synthetic or toy tasks are excluded. Each task must:

- Have a verifiable ground truth (passing tests, correct lint output)
- Be completable within 30-45 minutes by a skilled developer
- Exercise the task category meaningfully (no trivial one-line fixes for "multi-file")

### Categories and distribution

| Category | Count | Rationale |
|----------|-------|-----------|
| bug-fix | 14 | Most common real-world task; includes test-first diagnosis and performance bugs |
| feature-addition | 12 | Extension points, ambiguous requirements, infrastructure, documentation |
| refactoring | 12 | Semantic preservation, performance optimization, CI/CD config |
| code-review | 10 | Security review (report-only), concurrency analysis, migration guides |
| debugging | 11 | Hypothesis generation, regression bisection, profiling, stack traces |
| multi-file | 10 | Cross-module reasoning, merge conflicts, dependency migration |
| legacy-code | 12 | Modernization, large codebase navigation, deprecation patterns |

### Difficulty levels

- **easy** (19 tasks) - Single file, under 50 lines changed, obvious fix
- **medium** (29 tasks) - 1-3 files, moderate reasoning required
- **hard** (32 tasks) - Multiple files, non-obvious root cause, architectural decisions

### Capability mapping

Each task maps to 1-3 capabilities from a fixed taxonomy. This enables capability radar charts showing tool strengths and weaknesses:

| Capability | Tasks | What it measures |
|------------|-------|-----------------|
| code_comprehension | 41 | Understanding existing code before modifying |
| framework_knowledge | 35 | Knowing API patterns (Pydantic v2, async SQLAlchemy, etc.) |
| bug_diagnosis | 26 | Structured root cause analysis, test-first diagnosis |
| refactoring_discipline | 26 | Changing code without breaking behavior |
| multi_file_reasoning | 23 | Coordinating changes across multiple files |
| test_writing | 10 | Writing correct, meaningful tests |
| security_awareness | 10 | Identifying and fixing security vulnerabilities |
| cost_discipline | derived | Token efficiency across all tasks |

### Language distribution

59 Python tasks, 1 TypeScript task. Python tasks use modern frameworks (FastAPI, httpx, Flask, Click, Starlette, Pydantic, SQLAlchemy 2.0) with venv-based setup. TypeScript uses Hono with npm.

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

### Weight profiles

Three built-in profiles in `awb/scoring/weights.yaml`:

```yaml
default:
  correctness: 0.55
  cost_efficiency: 0.15
  speed: 0.10
  code_quality: 0.10
  reliability: 0.05
  security: 0.03
  efficiency: 0.02
```

### Statistical framework

- **Confidence intervals**: t-distribution based (no scipy required). Reports mean, 95% CI lower/upper, standard deviation, and sufficiency flag.
- **Significance testing**: Sign test for paired comparison of two tools on shared tasks. Reports p-value, Cohen's d effect size, and interpretation.
- **Integrity checks**: Contamination detection (completions <10s with success), variance anomalies (identical times/tokens across runs suggesting cached replay).

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
