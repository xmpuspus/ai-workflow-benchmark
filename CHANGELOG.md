# Changelog

## 1.1.0 (2026-04-07)

Performance and token optimization release. Cuts full-run wall clock by 33-50% and enables sub-$5 quick evaluations.

### Speed
- **Workspace template cache** (`~/.cache/awb/templates/`) — pip install runs once per unique (repo, commit, setup) combo; subsequent tasks copy the template (~2s vs ~45s). Saves ~55 min on a full run with 74 FastAPI tasks.
- **`awb warmup`** — pre-build all unique workspace templates before benchmarking
- **`--use-uv`** flag — rewrite `pip install` to `uv pip install` for 10-30x faster dependency installs
- **Parallel partial credit evaluation** — independent grep/file checks run concurrently via asyncio.gather; pytest-based criteria still run sequentially (shared venv state)
- **Adaptive timeout tightening** — runs 2+ use `min(original, 2x run1_actual)` to prevent 900s hangs on tasks that took 45s

### Token efficiency
- **Progressive execution** (`--progressive`) — runs easy tasks first, stops if easy pass rate < 40% or medium pass rate < 20%. Saves 50-80% of tokens on weak tools.
- **Fast-check mode** (`--fast-check`) — runs 8 representative tasks (1 per category) with 1 run. ~15 min and ~$4 vs ~3 hrs and ~$150 for a full suite. Reports estimated full-suite score with confidence margin.
- **Token budget enforcement** — new `max_input_tokens` and `max_output_tokens` fields in task constraints. Adapter streams events in real-time and kills the process if budget exceeded.
- **Streaming token monitor** — Claude Code adapter now parses stream events as they arrive (not post-hoc), enabling live budget checks and future per-iteration analysis.

### Scoring
- **Richer RunCost** — new fields: `cache_read_tokens`, `cache_creation_tokens`, `thinking_tokens`. Backward compatible (additive).
- **Token efficiency in composite score** — the `efficiency` dimension now blends 50% iteration count + 50% tokens-per-iteration via a new sigmoid normalizer (optimal=2k tokens/iter, baseline=15k).
- **Two new weight profiles**:
  - `token_efficient` — 25% cost weight, 15% efficiency (up from 2%)
  - `rate_limited` — 30% cost weight, for evaluating tools under tight API limits
- **Token-aware gap analysis** — detects cost-per-point outliers (3x median), low cache hit rates (<30%), and cost-inefficient failures.

### Results
- **JSONL output** — alongside per-file JSON, each run also appends to `{base_run_id}.jsonl` for fast batch loading. Backward compatible.
- **`load_jsonl()`** on ResultRecorder for faster analysis across many tasks.

### Tests
- 184 tests (up from 135) covering template cache, parallel verification, fast-check, streaming, token budget, new scoring profiles, and JSONL roundtrip.

## 1.0.9 (2026-04-04)

- Add Python 3.13 and 3.14 to CI test matrix and PyPI classifiers

## 1.0.8 (2026-04-04)

- Sync README changelog with PyPI long description
- Update GitHub repo description (80 → 100 tasks, 12 capability dimensions)
- Set GitHub homepage URL to PyPI

## 1.0.7 (2026-04-04)

Product audit fixes: 27 findings across observability, scoring, reliability, performance, and CLI safety.

### Observability
- Add `--verbose` flag to enable debug logging across all commands
- Save test output to `{run_dir}/{task_id}_{tool}.log` for post-mortem analysis
- Capture partial credit check output instead of discarding to /dev/null
- Replace bare `except Exception` in runner with specific handlers (TaskTimeoutError, RuntimeError for setup, NotImplementedError for stubs)
- Wire integrity checks (contamination + variance anomaly detection) into `awb run` output

### Scoring
- Add `SECURITY_METHODOLOGY` to Capability enum (was in schema but missing from code)
- Fix `normalize_quality` to use signed lint delta — negative deltas (lint improvements) now score correctly
- Remove hardcoded `METRIC_WEIGHTS` from config.py; all callers use `load_weight_profile()` from weights.yaml
- Fix timeout calibrator to allow increasing timeouts when p95 data shows tasks need more time
- Leaderboard uses per-task `compute_aggregate_score` instead of legacy `compute_composite_score`

### Reliability
- Handle `KeyboardInterrupt` gracefully in `awb run` — partial results preserved
- Guard against `load_single()` returning None during resume
- Fix `find_incomplete_run` to scan all `_runN` directories, not just `_run1`
- Add 600s timeout to repo setup commands
- Use `return_exceptions=True` in parallel gather to isolate task failures
- Move workspace cleanup into `finally` block

### Performance
- Add bare-clone cache (`~/.cache/awb/clones/`) — `git clone --mirror` then `git clone --local`
- Cache `RunEnvironment()` and adapter instance in `BenchmarkRunner.__init__`
- Add module-level schema cache to `task_loader._load_schema()`

### CLI Safety
- Add confirmation prompt before full-suite runs; skip with `--yes`
- Change `awb quickstart` to environment-only check (tools, auth, tasks, results writable)
- Print actual resolved results path instead of glob pattern
- Add `check_available()` guard; raise `UsageError` for stub adapters

## 1.0.6 (2026-04-03)

- Add trustme to 4 real httpx repo tasks (BF-003, BF-011, BF-013, FA-005)

## 1.0.5 (2026-04-02)

- Add trio to 16 httpx-based tasks (fixes silent pytest crash on Python 3.13+)

## 1.0.4 (2026-04-01)

- Fix 4 verification bugs (FA-010, RF-012, CR-007, BF-003)

## 1.0.0 (2026-03-26)

### Added
- CLI modularized: `awb/cli.py` (948 lines) split into 9 focused modules in `awb/commands/` (`run.py`, `analyze.py`, `calibrate.py`, `leaderboard_cmd.py`, `migrate.py`, `submit.py`, `validate.py`, `workflow_cmd.py`, `_shared.py`)
- 4 new adapters: Gemini CLI (`gemini-cli`), Codex CLI (`codex-cli`), Windsurf (stub), Copilot (stub) — joining claude-code-vanilla, claude-code-custom, pi, cursor (stub), aider (stub)
- `awb migrate-results` command to convert v0.5.x result JSON files to v1.0 format
- Result format v1.0: all result JSON now includes a `version: "1.0"` field and `config_hash` persisted in workflow metadata
- 11 capabilities (was 8): added `completeness_tracking`, `convention_adherence`, `context_discovery` alongside the existing 8; `security_methodology` was added in v0.5.0
- Weight sum validation: `awb run` raises a clear error if a custom weight profile does not sum to 1.0
- Color-coded terminal score output: green (≥80), yellow (50–79), red (<50) for partial credit scores
- Configurable model pricing: `MODEL_PRICING` dict in `awb/core/metrics.py` covers Opus, Sonnet, and Haiku tiers
- Chart.js radar chart on the leaderboard HTML page, CSV export button, and history tracking in `data/history.json`
- Metric names aligned across `composite.py` and `weights.yaml` (was mismatched in v0.5.x, causing silent weight misapplication)

### Changed
- Task loader logs skipped files rather than silently ignoring them
- Auth check uses the adapter's `supports_auth_check()` / `check_auth()` ABC methods instead of `hasattr` duck-typing
- Test suite: 75 → 135 tests

### Adapter ABC extensions
New optional methods on `ToolAdapter`: `supports_auth_check()`, `check_auth()`, `supports_streaming()`, `get_model_pricing()`

## 0.5.5 (2026-03-26)

### Added
- Pre-flight auth check before benchmark runs — detects "Not logged in" and exits with clear instructions instead of silently scoring 0
- Adapter prints claude stderr to console when it fails (visible red error message)

## 0.5.4 (2026-03-25)

### Fixed
- Package build now includes awb.analysis module (was excluded by .gitignore pattern matching awb/analysis/)
- Adapter logs stderr when claude exits with non-zero code instead of silently discarding errors

## 0.5.3 (2026-03-24)

### Changed
- Vanilla adapter now uses `--system-prompt` override and `CLAUDE_SKIP_HOOKS=1` for clean isolation — hooks, skills, and auto-memory are disabled while auth remains functional
- Workflow task setup reliability: valid repo commits, grep-based verification checks, calibrated difficulty

## 0.5.0 (2026-03-24)

### Added
- New **workflow** task category (30 tasks: WF-001 to WF-030) testing completeness tracking, convention discovery, security methodology, context utilization, async safety, dead code removal, config extraction, test-driven implementation, structured debugging, and more
- `workspace_claude_md` field in task schema — injects project-level CLAUDE.md into workspaces for tasks that test context discovery
- New capabilities: `completeness_tracking`, `convention_adherence`, `context_discovery`, `security_methodology`
- Benchmark grows from 80 to 100 tasks — workflow category is 30% of total score

### Changed
- Removed 10 zero-signal tasks that never passed or had extreme variance

### Removed
- FA-003, FA-011, FA-012 (high variance or broken verification)
- BF-007 (race condition too complex for one-shot)
- RF-004 (high variance)
- CR-006 (overly specific criterion)
- DB-004 (too hard, no differentiation)
- MF-002, MF-008, MF-010 (too hard or too noisy)

## 0.4.1 (2026-03-24)

### Added
- Resume auto-detection: `--resume` finds the most recent incomplete run automatically
- Git clone retry with exponential backoff (3 attempts, 5s/10s delay) for concurrent runs
- Split 7 single-criterion bottleneck tasks into granular partial credit (binary "Tests pass" → "At least half pass" + "All pass")

### Changed
- Default concurrency raised from 3 to 4 (`-j 4`)
- FA-011 verification criteria broadened to accept Google-style docstrings and inline parameter descriptions
- Difficulty labels recalibrated from empirical pass rates across 5 runs (easy >70%, medium 35-70%, hard <35%)

### Fixed
- FA-011 scored 16% on average due to overly rigid regex for param/return documentation checks

## 0.3.0 (2026-03-22)

### Added
- 20 new real-world engineering tasks (80 total): test-first diagnosis, review-only analysis, performance profiling, regression bisection, ambiguous requirements, Dockerfile writing, documentation generation, TypeScript typing, merge conflict resolution, dependency migration, large codebase navigation, CI/CD config fixing
- Workflow Lift Score: primary benchmark output measuring custom vs vanilla difference with statistical significance, broken down by capability
- Coding-performance hooks now fire in benchmark mode (frustration-detector, stop-continuation, file-count-escalation) — these ARE the workflow being measured

### Changed
- Benchmark no longer disables workflow hooks — custom adapter runs with full coding-performance automation while vanilla runs with none, producing a true workflow contribution measurement
- CLAUDE.md execution discipline rules moved to top of file for maximum attention

### Fixed
- Benchmark guard correctly distinguishes ops hooks (skip in unfamiliar repos) from coding hooks (always fire)

## 0.2.0 (2026-03-22)

### Added

- 60-task benchmark suite across 7 categories: bug-fix, feature-addition, refactoring, code-review, debugging, multi-file, legacy-code
- Sigmoid normalization with per-task baselines — scores never go negative, smooth gradient above baseline
- Capability profiles: 8-dimension radar chart covering code comprehension, bug diagnosis, multi-file reasoning, framework knowledge, test writing, refactoring discipline, security awareness, and cost discipline
- Gap analysis engine with failure classification (timeout / test_error / partial_completion / code_error), systematic pattern detection, and ranked improvement suggestions
- Statistical framework: t-distribution confidence intervals, sign test significance testing, integrity checks (contamination detection, variance anomalies)
- External submission format with JSON schema for cross-tool comparison
- Hardware classification for fair speed comparisons within hardware tiers
- Configurable weight profiles: default, correctness_focused, production (`awb/scoring/weights.yaml`)
- CLI commands: `awb gap`, `awb export`, `awb submit`, `awb compare-submissions`, `awb quickstart`, `awb info`
- CLI filters: `--capability`, `--difficulty` for `awb run`
- PyPI publishing support (`pip install awb`)

### Changed

- Scoring: merged `success_rate` and `partial_credit` into a single `correctness` dimension weighted at 55%
- Normalization: sigmoid curve replaces linear — cost above baseline no longer collapses score to 0
- Per-task baselines derived from task difficulty instead of global constants
- Difficulty-weighted aggregation: hard=2.5×, medium=1.5×, easy=1.0×

## 0.1.0 (2026-03-20)

### Added

- Initial benchmark harness with 10 tasks
- Claude Code adapters: vanilla and custom variants
- Workflow descriptor system (export, validate, diff)
- Static HTML leaderboard generator
- Linear normalization with global baselines
