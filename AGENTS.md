# AWB Development Guide

## Repository map

- `awb/adapters/` has tool integrations. Real adapters stream normalized events through the `on_event` callback so token budgets and traces work.
- `awb/core/` has task loading, repository preparation, execution, metrics, and result persistence.
- `awb/harness/` powers the free static stage of `awb checkup` for Claude Code and Codex instruction, config, and hook files.
- `awb/trace/` translates tool JSONL into OpenTelemetry-aligned spans and grades deterministic workflow behaviors.
- `awb/scoring/` and `awb/analysis/` turn run results into composite, readiness, lift, drift, cost, profile, and prescription reports.
- `awb/tasks/` has 100 pinned task definitions across 8 categories.
- `tests/` is the pytest suite. Read the relevant tests before editing tested code.

## Development commands

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check awb/ tests/
awb validate
```

The repository targets Python 3.11 and newer, uses dataclasses for data structures, Click for the CLI, Rich for text output, and a 100-character Ruff line limit.

## Implementation rules

- Preserve result and workflow schema compatibility unless the requested change explicitly needs a versioned break.
- Every adapter must implement the `ToolAdapter.execute(..., on_event=...)` signature. Streaming adapters call the callback as each event arrives and stop when it returns `False`.
- Async adapters must drain or cancel subprocess reader tasks in `finally`. A timeout must stop the subprocess group and return exit code 124.
- Do not let trace translation crash a benchmark run. Ignore unsupported or malformed events. Report `None` for a trace with no gradeable spans.
- Checkup verdicts are conservative. Weak evidence becomes `UNTESTED`, not `HELD` or `BROKEN`.
- Escape all user-file-derived strings before interpolating them into Rich markup.
- Keep exit codes stable for gating commands: 0 clean, 1 findings, 2 tool or environment failure.
- Task partial-credit criteria must total 100 points. Keep repository commits pinned.

## Codex support

- Use `codex exec --json` for non-interactive runs. `stdout` is JSONL and `stderr` is diagnostic progress.
- The configured Codex harness lives under `CODEX_HOME`, normally `~/.codex`. Do not read or hash `auth.json`, session logs, state databases, or credentials.
- Codex project instructions use `AGENTS.override.md` or `AGENTS.md`. AWB also writes task `workspace_claude_md` content to `AGENTS.override.md`. Claude Code and Codex then receive equivalent task context.
- `awb checkup --tool codex-cli` inspects Codex `AGENTS.md`, `config.toml`, `hooks.json`, and rules. Paired Codex runs need a separate authenticated baseline `CODEX_HOME`. Do not disable user safety rules to manufacture a vanilla baseline.

## Verification

For changes spanning three or more requirements, keep an explicit checklist. Before declaring completion, run focused tests, the full suite, Ruff, `awb validate`, and inspect `git diff --name-only` for scope.
