# Contributing to AWB

## Adding a Task

1. Copy `awb/tasks/_template.yaml`
2. Place in the correct category directory: `awb/tasks/<category>/`
3. Use a real OSS repo at a pinned commit SHA (not a branch name)
4. Include 4–7 partial credit criteria summing to exactly 100 points
5. Add 1–3 capabilities from the valid set below
6. Run `awb validate` to check your task
7. Submit a PR

### Valid Categories

`bug-fix`, `feature-addition`, `refactoring`, `code-review`, `debugging`, `multi-file`, `legacy-code`

### Valid Capabilities

`code_comprehension`, `bug_diagnosis`, `multi_file_reasoning`, `framework_knowledge`, `test_writing`, `refactoring_discipline`, `security_awareness`

### Task ID Format

2-letter category prefix + 3-digit number: `BF-012`, `LC-011`, `MF-009`

| Category | Prefix | Current range |
|----------|--------|---------------|
| bug-fix | BF | 001–011 |
| feature-addition | FA | 001–008 |
| refactoring | RF | 001–010 |
| code-review | CR | 001–007 |
| debugging | DB | 001–007 |
| multi-file | MF | 001–008 |
| legacy-code | LC | 001–010 |

Use the next available number in the range.

### Task Quality Checklist

- [ ] Repo pinned to a commit SHA, not a branch
- [ ] `estimated_minutes` is realistic for a skilled developer (not an AI)
- [ ] `partial_credit` criteria sum to 100
- [ ] Each `check` field is a shell command that exits 0 on pass
- [ ] `test_commands` are deterministic (no flaky network calls)
- [ ] Task is completable within `timeout_seconds`
- [ ] `awb validate` passes with no errors

## Adding a Tool Adapter

1. Create `awb/adapters/my_tool.py` implementing the `ToolAdapter` ABC
2. Register in `awb/adapters/registry.py`
3. Add an entry point in `pyproject.toml` under `[project.entry-points."awb.adapters"]`

Stubs for Cursor and Aider already exist — see `awb/adapters/cursor.py` for the minimal structure.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check awb/
```

All 71 tests must pass. New features need at least one happy-path test. Bug fixes need a regression test.

## Submitting Results

Run the benchmark, export, and share via PR to the `results/` directory or as a GitHub issue attachment:

```bash
awb run --runs 3
awb export results/runs/<run_dir>/ -o my-results.json
```

Include in your PR or issue:
- Tool name and version (`awb tools` output)
- Model identifier
- Hardware class (`awb quickstart` reports this)
- The exported `my-results.json`

## Code Style

- Python 3.11+, ruff for linting, 100-character line length
- Dataclasses for data structures (not Pydantic — minimal dependencies)
- Match existing patterns: Click for CLI, Rich for terminal output
- Test names: `test_<what>_<condition>` (e.g., `test_sigmoid_never_negative`)
- No docstrings on obvious functions
