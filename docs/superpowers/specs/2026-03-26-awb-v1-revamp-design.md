# AWB v1.0 Full Revamp Design

## Overview

Comprehensive overhaul of the AI Workflow Benchmark project: internal quality improvements, 4 new tool adapters (Gemini CLI, Codex CLI, Windsurf, Copilot), upgraded terminal output, polished static leaderboard, and task quality refinement. Clean break from v0.5.x with migration path for existing results.

## Approach

Foundation-first: refactor internals and add tests before building new features, so adapters and output upgrades land on stable ground. Five phases executed sequentially.

## Phase 1: Package Restructuring

### CLI Modularization

Break `awb/cli.py` (948 lines, 22 functions, 18 commands) into focused command modules:

```
awb/
├── cli.py                  # ~50 lines: Click group, imports from commands/
├── commands/
│   ├── __init__.py
│   ├── run.py              # awb run, _run_both(), comparison mode
│   ├── analyze.py          # awb gap, awb compare, awb stability
│   ├── calibrate.py        # awb calibrate-difficulty, calibrate-timeouts
│   ├── submit.py           # awb submit, compare-submissions, export
│   ├── validate.py         # awb validate, awb info, awb tools
│   ├── leaderboard.py      # awb leaderboard
│   ├── workflow.py          # awb workflow export/validate/diff/init
│   └── migrate.py          # awb migrate-results (new)
```

Each module registers Click commands with the main group. `cli.py` becomes a thin entry point.

### Import Cleanup

- Move `load_all_tasks` imports to module level (currently duplicated 3+ times in cli.py)
- Resolve circular dependency chains that forced lazy imports in the first place

### Error Handling Fixes

- `load_all_tasks()`: Replace bare `except Exception: continue` with specific catches (`ValidationError`, `yaml.YAMLError`) + `logger.warning()` for skipped tasks
- `hasattr(adapter, '_get_cmd')` in auth check: Replace with `adapter.supports_auth_check()` method on ABC

### Dead Code Removal

- Remove unused `_VANILLA_CONFIG_DIR` constant from `claude_code.py`
- Remove or deprecate `_load_default_weights()` from `config.py`
- Mark `compute_composite_score()` legacy interface with deprecation warning or remove if no external consumers

### Behavioral Guarantee

All existing command names, flags, and output formats remain identical after Phase 1. Phase 5 later upgrades terminal output (live progress, color-coded tables) — but that's a separate, additive change on top of the restructured codebase.

## Phase 2: Scoring System Fixes

### 2a. Capability Enum Alignment

Add 3 missing capabilities to `capabilities.py` enum:
- `completeness_tracking`
- `convention_adherence`
- `context_discovery`

Update capability profiling to compute scores for all 11 capabilities defined in schema.json.

### 2b. Metric Naming Standardization

Canonical scoring dimensions (7, matching `weights.yaml`):

| Dimension | Weight (default) | Source |
|-----------|-----------------|--------|
| correctness | 0.55 | 60% success_rate + 40% partial_credit |
| cost_efficiency | 0.15 | sigmoid(USD vs baseline) |
| speed | 0.10 | sigmoid(wall_clock vs estimated_minutes) |
| code_quality | 0.10 | sigmoid(lint_delta) |
| reliability | 0.05 | sigmoid(test_regressions) |
| security | 0.03 | sigmoid(security_delta) |
| efficiency | 0.02 | sigmoid(iteration_count vs max) |

`report.py` aligns to these 7 names. `success_rate` and `partial_credit` become internal components of `correctness`, not separate scoring dimensions.

### 2c. Result Format v1.0

Add `"version": "1.0"` field to all result JSON files. Schema changes:
- Metric keys match `weights.yaml` dimension names exactly
- Per-task capability scores included (not just aggregate)
- `hardware` field (optional, for cross-submission fairness)
- `adapter_config_hash` persisted in every result (already computed, not always saved)

### 2d. Bug Fixes

- `statistics.py` line 91: `zip(..., strict=False)` → `strict=True` for data integrity
- `composite.py`: Add assertion that loaded weight profile sums to 1.0
- `integrity.py`: Extract magic number `10` → `MIN_PLAUSIBLE_SECONDS = 10` constant
- `metrics.py`: Replace hardcoded Opus pricing with configurable dict:
  ```python
  MODEL_PRICING = {
      "opus": {"input_per_m": 15.0, "output_per_m": 75.0},
      "sonnet": {"input_per_m": 3.0, "output_per_m": 15.0},
      "haiku": {"input_per_m": 0.25, "output_per_m": 1.25},
      "default": {"input_per_m": 15.0, "output_per_m": 75.0},
  }
  ```
- `schema.json`: Add validation that partial_credit points sum to 100 (currently only enforced in code)

## Phase 3: Test Coverage

### Strategy

Prioritize by risk. Target ~80% coverage of critical paths. Behavioral tests with realistic fixtures. No mocking of the thing being tested.

### Tier 1 — Must Test

**runner.py:**
- Resume with matching task set → resumes correctly
- Resume with mismatched task filters → does not match
- Adaptive skip: task scoring 0 → classified decisive, not re-run
- Adaptive skip: task scoring 80% → classified near-miss, re-run
- Parallel execution with semaphore limiting

Uses `FakeAdapter` that returns canned `ToolResult` objects.

**results.py:**
- Write result → read back → identical
- `find_incomplete_run()` with various states (complete, partial, empty)
- Result directory creation and file naming

**metrics.py:**
- Known token counts → expected USD at Opus pricing
- Known token counts → expected USD at Sonnet pricing
- Zero tokens → $0.00

**code_review_scorer.py:**
- Perfect precision/recall → F1 = 1.0
- Zero matches → F1 = 0.0
- Partial matches → expected F1

### Tier 2 — Should Test

- `gap_analysis.py`: Known failure patterns → expected categorization
- `ingest.py`: Valid submission JSON → parsed correctly; invalid → error
- `compare.py`: Two submissions with known scores → expected comparison
- `lint_checker.py`: Sample lint output → correct issue count

### Tier 3 — Nice to Have

- `difficulty_calibrator.py`, `timeout_calibrator.py`: Synthetic run data → expected recalibration
- `leaderboard/generate.py`: Doesn't crash on valid input
- CLI integration: `awb validate` on known good/bad tasks

### New Fixtures (conftest.py)

- `sample_results_batch()`: Multiple results with varied outcomes
- `sample_task_set()`: Tasks at easy/medium/hard difficulty
- `fake_adapter()`: Configurable canned ToolResult returns

## Phase 4: Adapter System

### ABC Extensions

```python
class ToolAdapter(abc.ABC):
    name: str
    display_name: str

    # Existing (unchanged)
    @abc.abstractmethod
    async def execute(self, prompt: str, workspace: Path,
                      max_turns: int, timeout_seconds: int) -> ToolResult: ...
    @abc.abstractmethod
    def check_available(self) -> bool: ...
    @abc.abstractmethod
    def get_config_hash(self) -> str: ...

    # New optional capabilities
    def supports_auth_check(self) -> bool:
        return False

    async def check_auth(self) -> tuple[bool, str]:
        return True, ""

    def supports_streaming(self) -> bool:
        return False

    def get_model_pricing(self) -> dict[str, float]:
        return MODEL_PRICING["default"]
```

### New Adapters

**GeminiCliAdapter** (`awb/adapters/gemini_cli.py`):
- Invokes `gemini` CLI
- Isolation via `--no-extensions` or equivalent
- Parses Gemini's output format for metrics (tokens, tool calls)
- `check_available()`: `which gemini` + version check

**CodexCliAdapter** (`awb/adapters/codex_cli.py`):
- Invokes `codex` CLI (OpenAI)
- Isolation via clean config directory / `--no-plugins`
- Parses Codex output for metrics
- `check_available()`: `which codex` + version check

**WindsurfAdapter** (`awb/adapters/windsurf.py`):
- Requires research spike: Windsurf may not have a stable CLI mode. If no CLI exists, implement as a stub (like current Aider/Cursor) with a clear "requires Windsurf CLI vX+" message, and revisit when CLI ships.
- If CLI exists: invoke it with isolation flags, parse output for metrics
- `check_available()`: detect Windsurf installation + CLI presence

**CopilotCliAdapter** (`awb/adapters/copilot_cli.py`):
- Invokes `gh copilot` via GitHub CLI
- Constraint: Copilot CLI is suggestion-based (not agentic like Claude Code). The adapter wraps the AWB task prompt into a Copilot-compatible format: feeds the issue description as context, requests code changes, captures output. May require multiple invocations per task to approximate multi-turn interaction.
- `check_available()`: `gh extension list` check for copilot extension

### Adapter Registration

Update `pyproject.toml` entry points:
```toml
[project.entry-points."awb.adapters"]
claude-code-vanilla = "awb.adapters.claude_code:ClaudeCodeVanillaAdapter"
claude-code-custom = "awb.adapters.claude_code:ClaudeCodeCustomAdapter"
pi = "awb.adapters.pi:PiAdapter"
gemini-cli = "awb.adapters.gemini_cli:GeminiCliAdapter"
codex-cli = "awb.adapters.codex_cli:CodexCliAdapter"
windsurf = "awb.adapters.windsurf:WindsurfAdapter"
copilot = "awb.adapters.copilot_cli:CopilotCliAdapter"
```

Update `_FALLBACK` dict in `registry.py` to match.

### Adapter Testing

Each adapter gets:
- `test_check_available_when_missing()`: Tool not installed → returns False
- `test_config_hash_deterministic()`: Same config → same hash
- `test_execute_mock()`: Canned subprocess output → correct ToolResult parsing

## Phase 5: Output Upgrades

### 5a. Rich Terminal Output

**Live progress during `awb run`:**

Uses Rich `Live` display with a layout:
- Left panel: task list with status indicators (queued/running/pass/fail + score)
- Right panel: running totals (tasks complete, aggregate score, cost, elapsed time)
- Bottom: concurrency indicator ("4/4 slots active")

**Per-task mini-report:** As each task completes, print a one-line summary:
```
[PASS] BF-001 Fix response_model fields    82.3  $0.47  34s
[FAIL] MF-003 Cross-module refactor          0.0  $1.23  timeout
```

**Summary table:** Color-coded score bands:
- Green (>80): strong performance
- Yellow (50-80): room for improvement
- Red (<50): significant gaps

**Comparison mode:** Side-by-side columns with delta indicators:
```
                          vanilla    custom    delta
BF-001 response_model      62.1      82.3    +20.2 *
MF-003 cross-module          0.0       0.0      0.0
```
`*` = statistically significant difference.

No new dependencies. Rich already supports Live, Layout, Table with styles.

### 5b. Static Site Leaderboard

Upgrade from basic HTML to polished single-page static site.

**Technology:** Jinja2 templates + Chart.js (CDN, zero build step).

**Pages/views:**
- **Overview:** Tool comparison table with aggregate scores, radar chart overlay
- **Tool detail:** Per-task breakdown, 7-dimension radar chart, cost/speed scatter plot
- **Task explorer:** Filterable/sortable table of all 100 tasks, pass/fail per tool
- **History:** Score trend lines over time from multiple runs
- **Difficulty analysis:** Easy/medium/hard pass rates per tool as grouped bar chart

**Data layer:** Leaderboard generator writes JSON files to `data/` directory alongside `index.html`:
- `data/summary.json`: Aggregate scores per tool
- `data/tasks.json`: Per-task results per tool
- `data/history.json`: Historical runs index (appended on each `awb leaderboard` invocation)

**Run history tracking:** `awb leaderboard` reads all runs in `results/runs/`, builds historical index, generates trend data. Each invocation appends to `history.json` if new runs are found.

**Export:** "Download CSV" button on each view for data portability.

All client-side rendering. No server, no build step. Works from `file://` or any static hosting.

## Phase 6: Task Quality + Migration

### Task Improvements

**Operational steps** (run manually against accumulated benchmark data, not automated):
- Run `awb calibrate-difficulty` against accumulated results → re-rate tasks where empirical pass rates diverge >20% from labeled difficulty
- Run `awb calibrate-timeouts` → tighten timeouts for tasks consistently completing in <50% of allowed time

**Code/content changes:**
- Review tasks with 0% or 100% partial credit discrimination → add more granular criteria to create score spread
- Audit capability tag coverage: ensure all 11 capabilities appear across the task set with reasonable frequency
- Apply calibration output via `--apply` flags to update task YAML files

### Partial Credit Schema Enforcement

Add to `schema.json`:
```json
"partial_credit": {
  "type": "array",
  "items": { ... },
  "x-awb-points-sum": 100
}
```

Since JSON Schema can't natively express "array item field sum = N", enforce in `validate_task_yaml()` code and add a custom keyword annotation for documentation.

### Migration

New CLI command: `awb migrate-results <old_dir> [--output <new_dir>]`

Converts v0.5.x result JSON to v1.0 format:
- Adds `"version": "1.0"` field
- Renames metric keys to match canonical 7 dimensions
- Backfills missing fields (`hardware`, `adapter_config_hash`) with null
- Preserves all original data in `"_v05x_original"` key for auditability

One-time operation. Not a persistent compatibility layer.

## Non-Goals

- No web server / hosted dashboard (stays static)
- No task count expansion (keep 100, improve quality)
- No backward-compatible result loading (clean break + migration script)
- No additional scoring dimensions beyond the existing 7
- No real-time streaming API for results

## Success Criteria

- All 75 existing tests still pass after Phase 1-2
- Test count reaches 120+ after Phase 3 (45+ new tests)
- All 4 new adapters pass `check_available()` when tool is installed
- `awb run` shows live progress with Rich panels
- Leaderboard renders with Chart.js radar/bar/trend charts
- `awb migrate-results` converts v0.5.x results without data loss
- `awb validate` catches partial_credit sum != 100

## File Impact Estimate

| Phase | Files Modified | Files Created | Files Deleted |
|-------|---------------|---------------|---------------|
| 1. Restructure | 2 (cli.py, base.py) | 9 (commands/*.py) | 0 |
| 2. Scoring | 7 (capabilities, composite, report, statistics, integrity, metrics, schema) | 0 | 0 |
| 3. Tests | 1 (conftest.py) | 8 (test files) | 0 |
| 4. Adapters | 2 (registry.py, pyproject.toml) | 4 (adapter files) | 0 |
| 5. Output | 3 (run.py command, generate.py, templates) | 2 (new templates, static assets) | 0 |
| 6. Migration | 1 (schema.json) | 1 (migrate.py command) | 0 |
| **Total** | **~16** | **~24** | **0** |
