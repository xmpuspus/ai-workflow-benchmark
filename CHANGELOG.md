# Changelog

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
