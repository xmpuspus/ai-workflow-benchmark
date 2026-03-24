# Changelog

## 0.5.0 (2026-03-24)

### Added
- New **workflow** task category (10 tasks: WF-001 to WF-010) testing completeness tracking, convention discovery, security methodology, context utilization, and iterative test fixing
- `workspace_claude_md` field in task schema — injects project-level CLAUDE.md into workspaces for tasks that test context discovery
- New capabilities: `completeness_tracking`, `convention_adherence`, `context_discovery`, `security_methodology`

### Changed
- Replaced 10 zero-signal tasks with 10 workflow-differentiation tasks (stays at 80 total)

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
