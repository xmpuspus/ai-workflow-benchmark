# Changelog

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
