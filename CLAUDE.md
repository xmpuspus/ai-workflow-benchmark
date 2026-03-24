# AWB Development Guide

## Project Structure

- `awb/` — Main package
- `awb/tasks/` — Task YAML definitions (100 tasks across 8 categories)
- `awb/scoring/` — Sigmoid normalization, composite scoring, capability profiles, stability metrics, statistics
- `awb/analysis/` — Gap analysis engine, workflow improvement suggestions, difficulty/timeout calibrators
- `awb/submission/` — External submission format and cross-submission comparison
- `tests/` — pytest suite (75 tests)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check awb/
awb validate        # check all 80 task YAMLs against schema
```

Optional stats extras (for scipy-backed CI):
```bash
pip install -e ".[stats]"
```

## Conventions

- Python 3.11+, ruff for linting (100-char line length)
- Dataclasses for data structures — not Pydantic (minimal dependencies by design)
- Click for CLI, Rich for terminal output
- Tasks use real OSS repos at pinned commit SHAs
- All partial credit criteria must sum to 100 points
- Test names: `test_<what>_<condition>` (e.g., `test_sigmoid_never_negative`)

## Task Schema

See `awb/tasks/schema.json`. Required fields: `id`, `category`, `title`, `difficulty`, `estimated_minutes`, `languages`, `repo`, `issue`, `verification`, `constraints`. Optional: `tags`, `capabilities`, `workspace_claude_md`.

Valid categories: `bug-fix`, `feature-addition`, `refactoring`, `code-review`, `debugging`, `multi-file`, `legacy-code`, `workflow`

Valid capabilities: `code_comprehension`, `bug_diagnosis`, `multi_file_reasoning`, `framework_knowledge`, `test_writing`, `refactoring_discipline`, `security_awareness`, `completeness_tracking`, `convention_adherence`, `context_discovery`, `security_methodology`

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

New CLI commands in v0.4.0:
- `awb stability <run_dirs>...` — per-task score stability report
- `awb calibrate-difficulty <run_dirs>... [--apply]` — recalibrate difficulty from empirical pass rates
- `awb calibrate-timeouts <run_dirs>... [--apply]` — tighten timeouts from empirical p95 data

## Adding an Adapter

1. Implement `ToolAdapter` ABC in `awb/adapters/my_tool.py`
2. Register in `awb/adapters/registry.py`
3. Add entry point in `pyproject.toml` under `[project.entry-points."awb.adapters"]`
