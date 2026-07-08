# AWB Development Guide

## Project Structure

- `awb/` - Main package
- `awb/commands/` - CLI command modules (run, analyze, calibrate, leaderboard, migrate, submit, validate, workflow, trace, task_cmd, ab_cmd, drift_cmd, cost_cmd). Shared visual helpers live in `awb/commands/_shared.py` (color constants, score_style, bar, summary_table, headline_panel, emit_json).
- `awb/tasks/` - Task YAML definitions (100 tasks across 8 categories). Every task carries `provenance`, `contamination_risk`, `label` from the v1.2 schema; backfill via `scripts/backfill_provenance.py`.
- `awb/scoring/` - Sigmoid normalization, composite scoring, capability profiles, stability metrics, statistics, integrity checks, readiness composite, task-set hash, paired config A/B report (`ab.py`).
- `awb/analysis/` - Gap analysis engine, workflow improvement suggestions, prescriptions (rubric/capability failures to CLAUDE.md snippets), drift detection, cost-per-solved reports, difficulty/timeout calibrators.
- `awb/trace/` - OpenTelemetry-aligned `.trace.jsonl` artifact + the 4-rubric deterministic grader for `awb trace grade`.
- `awb/submission/` - External submission format and cross-submission comparison.
- `awb/adapters/` - Tool adapters. Stub adapters set `is_stub = True` (cursor, aider, windsurf, copilot) so the runner fails fast at startup. Real adapters using `asyncio.Event` must name their `create_task` instances and cancel them in `finally` (see claude_code.py for the pattern).
- `demos/` - `hero.tape` is the vhs recipe that produces `hero.gif`. Re-record on user-facing CLI changes; do NOT hand-paint GIFs.
- `results/baselines/` - Frozen per-release baselines published via the GitHub Pages workflow at `.github/workflows/leaderboard.yml`. Schema: `spec_version: awb/v2` plus `submission` + `results` blocks (see `results/baselines/README.md`).
- `scripts/` - `backfill_provenance.py` stamps provenance on every task YAML; `publish.sh` + `test_pypi_install.sh` are the release helpers.
- `tests/` - pytest suite (392 tests).

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check awb/
awb validate        # check all 100 task YAMLs against schema
```

Optional stats extras (for scipy-backed CI):
```bash
pip install -e ".[stats]"
```

## Conventions

- Python 3.11+, ruff for linting (100-char line length)
- Dataclasses for data structures - not Pydantic (minimal dependencies by design)
- Click for CLI, Rich for terminal output
- Tasks use real OSS repos at pinned commit SHAs
- All partial credit criteria must sum to 100 points
- Test names: `test_<what>_<condition>` (e.g., `test_sigmoid_never_negative`)

## CLI conventions (added v1.3)

- Color goes through the named constants in `awb/commands/_shared.py` (`OK`, `WARN`, `BAD`, `INFO`, `MUTED`). Don't write raw `[red]...[/red]` literals in command files.
- Score bars use `bar(score)` for Unicode block rendering; sample-size confidence uses `confidence_label(n)`.
- Every analysis command takes `--format text|json` (default text). JSON output uses the `emit_json` helper which dataclass-walks via `dataclasses.asdict`.
- `awb validate` defaults to a one-line summary; `-v/--verbose` restores the per-file PASS/FAIL list. Match this pattern when adding noisy commands.
- Production Readiness Score lives in `awb/scoring/readiness.py`; the heuristic constants (`REVIEW_BURDEN_FILES_TO_ZERO`, `COST_USD_TO_ZERO`, `SPEED_SECONDS_TO_ZERO`, `MAINTAINABILITY_LINT_TO_ZERO`) are extracted in `awb/commands/leaderboard_cmd.py` for tunability.

## Task Schema

See `awb/tasks/schema.json`. Required fields: `id`, `category`, `title`, `difficulty`, `estimated_minutes`, `languages`, `repo`, `issue`, `verification`, `constraints`. Optional: `tags`, `capabilities`, `workspace_claude_md`.

Valid categories: `bug-fix`, `feature-addition`, `refactoring`, `code-review`, `debugging`, `multi-file`, `legacy-code`, `workflow`

Valid capabilities: `code_comprehension`, `bug_diagnosis`, `multi_file_reasoning`, `framework_knowledge`, `test_writing`, `refactoring_discipline`, `security_awareness`, `completeness_tracking`, `convention_adherence`, `context_discovery`, `security_methodology`. `cost_discipline` is a derived capability computed from token efficiency across all tasks; it is not declared in YAML.

## Scoring

- Sigmoid: `score = 100 / (1 + exp(k * (value - baseline)))`
- Per-task baselines from `awb/scoring/baselines.py` (derived from difficulty)
- Weight profiles from `awb/scoring/weights.yaml` (default, correctness_focused, production)
- Composite = difficulty-weighted sum of 7 sigmoid-normalized dimensions
- Stability metric: `TaskStability` with std_dev, score_range, is_unstable flag; high-variance tasks can be optionally down-weighted in composite scoring

## Adding a Task

1. Copy `awb/tasks/_template.yaml` into the correct category subdirectory
2. Use next available ID in the category's range (check existing files)
3. Pin the repo to a commit SHA, not a branch name
4. Run `awb validate` before opening a PR

CLI commands:
- `awb stability <run_dirs>...` - per-task score stability report
- `awb calibrate-difficulty <run_dirs>... [--apply]` - recalibrate difficulty from empirical pass rates
- `awb calibrate-timeouts <run_dirs>... [--apply]` - tighten timeouts from empirical p95 data
- `awb migrate-results <old_dir>` - convert v0.5.x result JSON to v1.0 format

## Harness Tuning Commands (added v1.5)

- `awb task from-pr <pr_url> --out ./tasks` - mine a private task from a merged GitHub PR (gh CLI required). Pins the pre-merge SHA, overlays the PR's test files via setup_commands, validates against the schema before writing. Private tasks run via `awb run --tasks-dir ./tasks`.
- `awb ab <tool> --config-a <dir> --config-b <dir>` - same adapter, two config dirs (CLAUDE_CONFIG_DIR for claude-code-custom), paired sign test via `compare_tools_paired`. Adapters opt in with `supports_config_dir = True`.
- `awb drift <run_dir> --baseline <ref>` - reference is a run dir or an awb/v2 baseline JSON. Exit code contract: 1 on drift beyond `--threshold` (default 5.0), 0 otherwise; keep that stable, cron/CI depends on it.
- `awb cost <run_dirs>...` - cost per solved task; divides total spend (failed attempts included) by solves. `cost_per_solved` is None when nothing solved, never a division crash.
- `awb gap <run_dir> --prescribe` - appends prescriptions from `awb/analysis/prescriptions.py`; a rubric fires at score < 60 on 2+ tasks. Without the flag, gap output must stay byte-identical.

## Adding an Adapter

1. Implement `ToolAdapter` ABC in `awb/adapters/my_tool.py`
2. Register in `awb/adapters/registry.py`
3. Add entry point in `pyproject.toml` under `[project.entry-points."awb.adapters"]`
