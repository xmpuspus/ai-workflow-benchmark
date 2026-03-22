# AWB Development Guide

## Project Structure

- `awb/` — Main package
- `awb/tasks/` — Task YAML definitions (60 tasks across 7 categories)
- `awb/scoring/` — Sigmoid normalization, composite scoring, capability profiles, statistics
- `awb/analysis/` — Gap analysis engine, workflow improvement suggestions
- `awb/submission/` — External submission format and cross-submission comparison
- `tests/` — pytest suite (71 tests)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check awb/
awb validate        # check all 60 task YAMLs against schema
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

See `awb/tasks/schema.json`. Required fields: `id`, `category`, `title`, `difficulty`, `estimated_minutes`, `languages`, `repo`, `issue`, `verification`, `constraints`. Optional: `tags`, `capabilities`.

Valid categories: `bug-fix`, `feature-addition`, `refactoring`, `code-review`, `debugging`, `multi-file`, `legacy-code`

Valid capabilities: `code_comprehension`, `bug_diagnosis`, `multi_file_reasoning`, `framework_knowledge`, `test_writing`, `refactoring_discipline`, `security_awareness`

## Scoring

- Sigmoid: `score = 100 / (1 + exp(k * (value - baseline)))`
- Per-task baselines from `awb/scoring/baselines.py` (derived from difficulty)
- Weight profiles from `awb/scoring/weights.yaml` (default, correctness_focused, production)
- Composite = difficulty-weighted sum of 7 sigmoid-normalized dimensions

## Adding a Task

1. Copy `awb/tasks/_template.yaml` into the correct category subdirectory
2. Use next available ID in the category's range (check existing files)
3. Pin the repo to a commit SHA, not a branch name
4. Run `awb validate` before opening a PR

## Adding an Adapter

1. Implement `ToolAdapter` ABC in `awb/adapters/my_tool.py`
2. Register in `awb/adapters/registry.py`
3. Add entry point in `pyproject.toml` under `[project.entry-points."awb.adapters"]`
