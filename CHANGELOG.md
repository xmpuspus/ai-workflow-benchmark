# Changelog

## 1.6.0 (2026-07-23)

The checkup release: grade your harness design in minutes, with proof of which
rules actually fired.

### Added

- **`awb checkup`**: one command, three stages. Stage 0 parses CLAUDE.md,
  AGENTS.md, and settings.json with zero model calls: structural checks (hooks
  resolve, JSON valid, documented commands match the repo's build files) plus
  extraction of the harness's testable promises across 8 rule patterns, each
  tagged hook-enforced or prose-only. Stage 1 runs the 8-task fast-check probe
  in parallel and grades the traces. The report leads with a plain-language
  verdict, pillar scores, a rule-integrity table (HELD / BROKEN / ENFORCED /
  UNTESTED per stated rule, with a wrong verdict deliberately traded away for
  UNTESTED when signal is weak), and top fixes ranked by estimated impact.
  Broken prose rules escalate to a ready-to-paste hook recommendation.
  `--static-only` runs the free stage alone; `--paired` adds the vanilla arm
  and Workflow Lift; `--format json` for CI. Exit codes: 0 clean, 1 findings,
  2 tool failure, now documented as the project-wide contract.
- **Two new deterministic trace rubrics**: `context_discipline` (distinct
  files read vs the task's declared scope) and `tool_call_efficiency`
  (repeated reads and edit thrash), both derived from spans the runner already
  emits. Both submission schema copies accept the 6-rubric grades.
- **Prescriptions cover all 11 capabilities** (was 4) and carry
  `est. +N pts` impact estimates, sorted within severity, with an explicit
  caveat that independent estimates do not sum.
- **`--last-run` plumbing**: `awb run` and `awb checkup` record their run
  directory; `gap`, `cost`, `drift`, and `trace grade` fall back to it when
  the run-dir argument is omitted.
- **`awb warmup --fast-check`** warms only the repos of the 8 probe tasks.
- `awb gap` opens with a one-line verdict naming the worst capability and the
  top prescription.

### Fixed

- **`awb run --fast-check` with no tool name silently ran the full suite
  twice.** The tool-less comparison path dropped `--fast-check`,
  `--progressive`, `--use-uv`, and `--yes`, so the most natural first command
  executed 100 tasks x 3 runs x 2 variants (roughly $300 at the documented
  per-task rate) instead of 8 tasks for about $4. All four flags now forward,
  and both variants run the identical 8-task set.
- The comparison path now runs the same adapter availability and auth
  preflight as the tool path (fails in about a second instead of after the
  first workspace clone) and prompts before large runs with a cost estimate
  that accounts for both variants.
- Fast-check defaults to parallel execution at concurrency 4; an explicit
  `-j` always wins, including `-j 1` to force sequential.
- Six user-visible suggestion strings carried em-dashes; replaced with plain
  punctuation.

## 1.5.0 through 1.5.4 (2026-07-08, backfill)

These five releases shipped without changelog entries; recorded here for the
audit trail.

- **1.5.0**: the harness-tuning release. `awb task from-pr` (mine a private
  task from a merged GitHub PR, pre-merge SHA pinned, PR test files overlaid),
  `awb run --tasks-dir`, `awb ab` (paired config A/B with sign test),
  `awb drift` (regression watch with a stable exit-code contract), `awb cost`
  (dollars per solved task), `awb gap --prescribe` (CLAUDE.md snippet
  prescriptions).
- **1.5.1**: submission schema accepts the v1.4.0 trust columns (`readiness`,
  `trace_summary`, per-run `trace_grade`); both schema copies patched with a
  sync guard test.
- **1.5.2**: `trace_summary: null` (zero graded traces) validates.
- **1.5.3**: `task from-pr` passed per_page as a `gh api -F` field, silently
  turning the GET into a POST that GitHub 404s; moved to the query string.
- **1.5.4**: `awb run --dry-run` no longer pays the adapter auth preflight;
  previews are instant.

## 1.4.0 (2026-05-30)

Trust-fix release from a fresh product audit. The headline differentiator,
deterministic trace grading, was scoring 100 on every run because the runner
never emitted the spans the rubrics needed. This release makes the grader
actually grade (validated against a real fast-check run), fixes two silent
data-loss bugs in the runner, and tightens the storefront.

### Fixed

- **Trace grader was vacuous in production.** The runner only emitted
  `LLM_REQUEST` spans (plus a legacy top-level `tool_use` path real Claude Code
  never produces), so all four trace-grade rubrics fell through to their
  trivial-pass branches and scored 100 on every run. A new `TraceTranslator`
  walks the nested `tool_use` blocks in `assistant` content, emits
  `FILE_EDIT` / read `TOOL_USE` / `SHELL_COMMAND` spans, and correlates Bash
  exit codes from `tool_result` events. File paths are relativized against the
  workspace so `no_out_of_scope_edits` matches `files_to_examine`.
- **`-j N` was a silent no-op** without `--parallel`. `-j>1` now enables
  parallel mode on its own; `--parallel` alone fans out to 4; default stays
  sequential (`-j 1`).
- **Parallel-task crashes vanished from results.** A task that raised on the
  parallel path was only logged; it is now recorded as a FAIL with a
  traceback, and stub/usage errors abort the run like the sequential path.

### Added

- **Baseline export carries trust columns**: per-run `trace_grade` (null when a
  trace has no gradeable spans, so non-streaming tools don't get a fake 100)
  and a submission-level `readiness` block + `trace_summary`. The published
  `claude-code-custom-1.4.0-fast-check.json` now ships real, discriminating
  trace grades (`no_out_of_scope_edits` ranges 17-100 across the 8 tasks).
- **`grade_trace_or_none`** distinguishes a span-less trace from a genuinely
  perfect one. `readiness_from_results` is shared by the leaderboard and export.
- **Shell-execution trust boundary documented** in `docs/SECURITY.md`, with
  per-task Docker isolation scoped as the next step toward community submissions.

### Changed

- **Aider is a real adapter** (`is_stub = False`); it gates on the binary being
  installed. Aider's `--no-stream` means no trace spans, so its trace columns
  report `null`.
- **Runtime dependencies are exact-pinned** for reproducible installs.
- **Trace `file.path` is relativized through symlinked workspaces** (macOS
  `/tmp` -> `/private/tmp`), and `no_out_of_scope_edits` honors directory
  entries (`tests/`) in `files_to_examine` instead of exact-set membership.
- README refreshed to v1.4.0 (lead, install pin, baseline reference).

## 1.3.0 (2026-05-24)

Storefront and trust release: fixes credibility leaks in the docs, adds real
reliability + provenance data behind the v1.2 schema, polishes every CLI
output through one visual contract, and replaces 29 synthesized demo GIFs
with a single real recording.

### Added

- **`--format json`** on `awb gap`, `awb compare`, `awb stability`, and
  `awb leaderboard --readiness` so analysis output can be piped into
  scripts. Dataclass-aware JSON encoder via `awb/commands/_shared.py`.
- **`awb leaderboard --readiness --explain`** prints the 7 sub-scores per
  tool in a ranked Rich Panel; magic constants extracted (`REVIEW_BURDEN
  _FILES_TO_ZERO`, `COST_USD_TO_ZERO`, `SPEED_SECONDS_TO_ZERO`,
  `MAINTAINABILITY_LINT_TO_ZERO`).
- **`awb validate`** defaults to a one-line summary; `-v/--verbose`
  restores per-file PASS/FAIL.
- **`is_stub` adapter attribute**: stub adapters now fail fast at startup
  before workspace provisioning instead of crashing mid-run. Cursor,
  Aider, Windsurf, Copilot all carry `is_stub = True` until validated.
- **Real `aider` adapter implementation**: `aider --message --yes
  --no-stream`. Marked `is_stub = True` pending an end-to-end run.
- **`RunEnvironment` records** `python_version`, `awb_version`,
  `adapter_version`, `pip_freeze_hash` (sha256 prefix of sorted
  `pip freeze`) for full reproducibility provenance.
- **`RunError` dataclass + `RunOutcome.error`**: a crash now lands in
  the result with `exc_type`, `exc_message`, and the last 8 traceback
  lines so it is distinguishable from a real low-score run.
- **`scripts/backfill_provenance.py`** stamped every task YAML with
  `provenance.{created_at, last_verified_at}`, `contamination_risk: high`,
  and `label: synthetic_overlay`. The v1.2 trust framing is now backed by
  data on all 100 tasks.
- **Visual contract** in `awb/commands/_shared.py`: project-wide color
  constants (OK/WARN/BAD/INFO/MUTED), `score_style`, `confidence_label`,
  Unicode block `bar()`, `summary_table`, `headline_panel`, `emit_json`.
- **`CITATION.cff`** + **`codemeta.json`** at repo root for academic
  citation. README "Citing AWB" section with BibTeX template.
- **`METHODOLOGY.md` "Related work"** cites HAL (arXiv:2510.11977),
  SWE-bench (arXiv:2310.06770), SWE-bench Pro (arXiv:2509.16941),
  LiveCodeBench (arXiv:2403.07974), METR RE-Bench (arXiv:2411.15114),
  Aider Polyglot, Artificial Analysis, and Cohen 1988.
- **`docs/zenodo-doi.md`** documents the one-time GitHub-Zenodo setup
  and per-release DOI mint recipe.
- **`.github/workflows/leaderboard.yml`** deploys
  `results/baselines/*.json` plus the static HTML to GitHub Pages on push.
- **Reproducible demo recipe** in the README Quick Start.

### Fixed

- **JSONL append race under `--parallel`** (`awb/core/results.py`):
  wrap `_append_jsonl` in `fcntl.LOCK_EX` so 5-15KB result records do
  not interleave (POSIX atomic-append only covers <PIPE_BUF). Regression
  test writes 100 concurrent ~8KB records and asserts 100 valid JSON
  lines.
- **Git operations had no timeout** (`awb/core/repo_manager.py`):
  `_run` / `_run_shell` now take a `timeout=` kwarg, wrap
  `proc.communicate()` in `asyncio.wait_for`, kill on `TimeoutError`.
  Sync git helpers (`get_diff`, `get_modified_files`, `get_lines_
  changed`) pass `timeout=60` to `subprocess.run`. A flaky network can
  no longer hang the whole runner.
- **`pi` adapter blocked the event loop** (`awb/adapters/pi.py`): the
  documented synchronous `Popen + communicate` body now runs inside
  `asyncio.to_thread` so `--parallel` mode is not single-threaded with
  extra steps.
- **Doc count drift**: capability counts in README/METHODOLOGY were off
  by 2-6 per row (`completeness_tracking` was claimed 10, actually 4).
  Difficulty tiers (`easy ~44 / med ~5 / hard ~31` summed to 80 not 100;
  actual is 48/17/35). Language distribution claimed "59 Python + 1
  TypeScript"; actual is 100 Python-touching tasks, zero TypeScript.
  Repos Used inflated by Pydantic, SQLAlchemy, and Hono which never
  appear as a `repo.url`.
- **Stale test count**: CLAUDE.md and CONTRIBUTING.md said "135 tests";
  actual is 246 (was 240 before this release).
- **ADAPTER.md** still claimed "60 tasks"; updated to 100.
- **ARCHITECTURE.md mermaid + tree** pointed at three filenames that
  do not exist (`scoring/stability.py`, `analysis/calibrate_*.py`).
  Renamed to actual files (`scoring/statistics.py`,
  `analysis/{difficulty,timeout}_calibrator.py`).
- **Misquoted Stack Overflow stat**: README hero claimed "trust
  collapsed from 40% to 29%"; replaced with the actual 2025 figure
  (33% trust, 46% distrust).
- **Broken SWE-bench Pro link**: pointed at the umbrella landing page;
  fixed to <https://scaleapi.github.io/SWE-bench_Pro-os/> with
  arXiv:2509.16941 citation.

### Changed

- **Capability profile rendering**: `=` ASCII bars replaced with Unicode
  block bars (`█░`) plus `(n, conf=high|med|low)` per row. "Top
  Improvement Actions" renamed to "Top Suggestions" so the README
  example finally matches actual CLI output.
- **`awb compare`** collapsed from 9 columns to 6 (Task, A, B, Score Δ,
  Time Δ, Cost Δ) with delta colors and a mean-Δ footer.
- **Production Readiness Score** renders as a Rich Panel with rank
  ordering and a "next step" pointer to `awb trace grade`.
- **Result schema**: `environment.{python_version, awb_version,
  adapter_version, pip_freeze_hash}` and `outcome.error` are now
  permitted optional fields. Backward-compatible with v1.2 records.
- **README hero hook** tightened from 27 words to 15. Em-dash cadence
  trimmed (three em-dashes in one paragraph was the classic AI tell).
- **Softened "first to" framing**: README "How AWB relates to other
  benchmarks" subsection concedes HAL and Artificial Analysis are
  already in adjacent territory and positions AWB's contribution as
  the deterministic, workflow-isolated complement.

### Removed

- 29 hand-painted Pillow-synthesized demo GIFs (3.2 MB) replaced by
  one real `vhs`-recorded `demos/hero.gif` (297 KB).
- The 5 `demos/make_*.py` synthesis scripts. New recipe lives in
  `demos/hero.tape`.
- 22 inline `<img src="demos/cli-*.gif">` and 8 link-only references
  from the README. README shrank from 526 to 498 lines.

### Tests

- 246 passing (was 240 in v1.2). Six new: JSONL concurrency race,
  stub-adapter attribute contract, plus existing regressions.

## 1.2.0 (2026-04-27)

Trust and differentiation release: fixes seven trust blockers from the v2 strategy, then ships the first v2 slice (task-set hash, fresh/verified metadata, OpenTelemetry-aligned trace artifact, `awb trace grade`, Production Readiness Score).

### Added (P1)

- **`task_set_hash`**: `awb.scoring.integrity.compute_task_set_hash()` walks the bundled tasks directory and returns a deterministic SHA-256 over (path, bytes) pairs. Stamped on every result so leaderboard rows can refuse to compare across mismatched task sets.
- **OpenTelemetry-aligned trace artifact**: new `awb/trace/` package writes a `<task_id>_<tool>.trace.jsonl` file beside each result. Spans use OTel GenAI conventions (`gen_ai.client.operation`, `gen_ai.tool.use`, `gen_ai.usage.input_tokens`, `gen_ai.tool.name`) plus AWB-specific names for shell commands, file edits, and test runs. The runner wires these via the existing adapter `on_event` callback; collectors can ingest the JSONL with no transform.
- **`awb trace grade <run_dir>`**: scores each trace.jsonl by four shipping disciplines (read tests before edit, ran verification after change, no out-of-scope edits, no repeated failing-command loop). Each score 0-100.
- **Production Readiness Score**: `awb.scoring.readiness.compute_readiness_score()` composite over 7 dimensions (correctness 35%, regression-safety 20%, security 15%, review-burden 10%, maintainability 8%, cost 7%, speed 5%). New `--readiness` flag on `awb leaderboard` prints per-tool composites to stdout.
- **Task provenance fields**: optional `provenance.{source_pr_url, created_at, last_verified_at}`, `contamination_risk` (`low`/`medium`/`high`/`unknown`), and `label` (`real_pr`/`synthetic_overlay`/`mutated`/`fresh`) on the task schema. Backward compatible: all 100 existing tasks validate unchanged.

### Fixed (P0 trust blockers)

- **Token budget fields no longer dropped** during YAML parse. `max_input_tokens` and `max_output_tokens` now flow from the task spec into `TaskConstraints`, enabling the runner's existing budget enforcement.
- **Workflow descriptor schema enum aligned with adapter registry**: schema now permits all 9 registered adapters (was 4). New guard test asserts the two stay in sync.
- **Setup cache key is now order-sensitive**: the previous `tuple(sorted(setup_commands))` collided two semantically-different setups; install order can change resolved deps. Extracted `_setup_cache_key()` helper.
- **Missing security scanner binary surfaces a warning instead of silent clean pass**: `bandit`/`semgrep` not installed used to return clean; now `run_security_scan` marks `all_clean=False` and annotates the output.
- **Adapter `on_event` is now properly typed** as `Callable[[dict], bool | None]` with documented event schema (assistant/tool_use/result, with usage shape). Exported `StreamEventCallback` alias.
- **Gap analysis classifier enriched**: two new categories: `regression_introduced` (when `quality.test_regressions > 0`) and `no_edits_made` (when `metrics.files_modified == 0`), each with their own suggestion rules.

### Changed

- **Result schema bumped to v2** (strict): `additionalProperties: false` at every level, required `schema_version=2`, required `task_set_hash` (sha256 hex), optional `trace_path`. The schema is bundled in the wheel as `awb/results-schema.json` so installed packages can validate offline.
- **`awb migrate-results` now handles v0.5.x → v1.0 → v2** in one pipeline. Idempotent on already-v2 records; backfills `task_set_hash` with a sentinel zero hash for legacy results.
- **`RunResult.to_dict()` emits `schema_version`, `task_set_hash`, and `trace_path`** alongside the legacy `version` key (kept for one release for backward compat with v1.x readers).
- **README opening rewritten** to lead with the v1.2 positioning and cite real sources (Stack Overflow 2025 Developer Survey, METR's July 2025 RCT, OpenAI's SWE-bench Verified contamination findings).
- **New hero demo GIF** at `demos/v12_trace_readiness.gif` shows the three new commands in 32pt Menlo so it reads cleanly on social embeds.

### Migration note

Existing v1.x result files are forward-compatible with v2 readers. To upgrade them in place: `awb migrate-results results/runs/`. New runs automatically write v2.

## 1.1.4 (2026-04-07)

Demo GIFs regenerated to reflect v1.1 features. Docs-only release.

- Fixed outdated `awb --version` output in `cli-version.gif` (was stuck at 1.0.0)
- Updated main `awb-showcase.gif` to show v1.1.3 and new speed features (warmup + fast-check scene)
- Added four new demo GIFs: `cli-warmup.gif`, `cli-fast-check.gif`, `cli-progressive.gif`, `cli-use-uv.gif`
- README embeds the new GIFs inline in the Execution Modes and `awb warmup` sections
- Regenerated all 18 existing `cli-*.gif` files via `demos/make_cli_demos.py` for consistent timestamps

No code changes.

## 1.1.3 (2026-04-07)

Release-hygiene follow-ups to the v1.1.x release train:

- **Single source of truth for version.** `pyproject.toml` now uses `dynamic = ["version"]` with `[tool.hatch.version] path = "awb/__init__.py"`, so `awb/__init__.py` is the only place the version lives. Fixes the v1.1.0 → v1.1.1 incident where the two files drifted.
- **`scripts/test_pypi_install.sh`**: release smoke test that installs the just-built wheel in a fresh venv and exercises every CLI command end-to-end (info, tools, validate, quickstart, warmup, run dry-runs, gap, compare, stability, calibrate-*, export, submit, compare-submissions, leaderboard, workflow export/validate/diff, migrate-results). Catches packaging bugs that editable dev installs hide. `scripts/publish.sh` now runs it automatically before `twine upload`.
- **Leaderboard default output path fix.** `awb leaderboard` previously wrote to `<package_install_dir>/awb/leaderboard/output/`, which broke on read-only installs and polluted site-packages. Now defaults to `./results/leaderboard/` in the current working directory, overridable with `--output-dir`.

## 1.1.2 (2026-04-07)

Packaging fixes found via exhaustive CLI smoke tests of the fresh PyPI install:

- Include `awb/workflow/schema.json` in the wheel (fixes `awb workflow validate`, `awb workflow diff`, `awb workflow init`)
- Include `awb/submission/schema.json` in the wheel: copied from `results/submission-schema.json`, loader now prefers the packaged copy and falls back to the repo layout (fixes `awb submit` and `awb compare-submissions` on installed versions)
- Both bugs were pre-existing in v1.0.x; v1.1.x inherited them. The fix is a hatch include list change plus a loader update.

## 1.1.1 (2026-04-07)

- Fix `awb/__init__.py` `__version__` string (was stuck at 1.0.9, now reports 1.1.1)

## 1.1.0 (2026-04-07)

Performance and token optimization release. Cuts full-run wall clock by 33-50% and enables sub-$5 quick evaluations.

### Speed
- **Workspace template cache** (`~/.cache/awb/templates/`): pip install runs once per unique (repo, commit, setup) combo; subsequent tasks copy the template (~2s vs ~45s). Saves ~55 min on a full run with 74 FastAPI tasks.
- **`awb warmup`**: pre-build all unique workspace templates before benchmarking
- **`--use-uv`** flag: rewrite `pip install` to `uv pip install` for 10-30x faster dependency installs
- **Parallel partial credit evaluation**: independent grep/file checks run concurrently via asyncio.gather; pytest-based criteria still run sequentially (shared venv state)
- **Adaptive timeout tightening**: runs 2+ use `min(original, 2x run1_actual)` to prevent 900s hangs on tasks that took 45s

### Token efficiency
- **Progressive execution** (`--progressive`): runs easy tasks first, stops if easy pass rate < 40% or medium pass rate < 20%. Saves 50-80% of tokens on weak tools.
- **Fast-check mode** (`--fast-check`): runs 8 representative tasks (1 per category) with 1 run. ~15 min and ~$4 vs ~3 hrs and ~$150 for a full suite. Reports estimated full-suite score with confidence margin.
- **Token budget enforcement**: new `max_input_tokens` and `max_output_tokens` fields in task constraints. Adapter streams events in real-time and kills the process if budget exceeded.
- **Streaming token monitor**: Claude Code adapter now parses stream events as they arrive (not post-hoc), enabling live budget checks and future per-iteration analysis.

### Scoring
- **Richer RunCost**: new fields: `cache_read_tokens`, `cache_creation_tokens`, `thinking_tokens`. Backward compatible (additive).
- **Token efficiency in composite score**: the `efficiency` dimension now blends 50% iteration count + 50% tokens-per-iteration via a new sigmoid normalizer (optimal=2k tokens/iter, baseline=15k).
- **Two new weight profiles**:
  - `token_efficient`: 25% cost weight, 15% efficiency (up from 2%)
  - `rate_limited`: 30% cost weight, for evaluating tools under tight API limits
- **Token-aware gap analysis**: detects cost-per-point outliers (3x median), low cache hit rates (<30%), and cost-inefficient failures.

### Results
- **JSONL output**: alongside per-file JSON, each run also appends to `{base_run_id}.jsonl` for fast batch loading. Backward compatible.
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
- Fix `normalize_quality` to use signed lint delta: negative deltas (lint improvements) now score correctly
- Remove hardcoded `METRIC_WEIGHTS` from config.py; all callers use `load_weight_profile()` from weights.yaml
- Fix timeout calibrator to allow increasing timeouts when p95 data shows tasks need more time
- Leaderboard uses per-task `compute_aggregate_score` instead of legacy `compute_composite_score`

### Reliability
- Handle `KeyboardInterrupt` gracefully in `awb run`: partial results preserved
- Guard against `load_single()` returning None during resume
- Fix `find_incomplete_run` to scan all `_runN` directories, not just `_run1`
- Add 600s timeout to repo setup commands
- Use `return_exceptions=True` in parallel gather to isolate task failures
- Move workspace cleanup into `finally` block

### Performance
- Add bare-clone cache (`~/.cache/awb/clones/`): `git clone --mirror` then `git clone --local`
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
- 4 new adapters: Gemini CLI (`gemini-cli`), Codex CLI (`codex-cli`), Windsurf (stub), Copilot (stub): joining claude-code-vanilla, claude-code-custom, pi, cursor (stub), aider (stub)
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
- Pre-flight auth check before benchmark runs: detects "Not logged in" and exits with clear instructions instead of silently scoring 0
- Adapter prints claude stderr to console when it fails (visible red error message)

## 0.5.4 (2026-03-25)

### Fixed
- Package build now includes awb.analysis module (was excluded by .gitignore pattern matching awb/analysis/)
- Adapter logs stderr when claude exits with non-zero code instead of silently discarding errors

## 0.5.3 (2026-03-24)

### Changed
- Vanilla adapter now uses `--system-prompt` override and `CLAUDE_SKIP_HOOKS=1` for clean isolation: hooks, skills, and auto-memory are disabled while auth remains functional
- Workflow task setup reliability: valid repo commits, grep-based verification checks, calibrated difficulty

## 0.5.0 (2026-03-24)

### Added
- New **workflow** task category (30 tasks: WF-001 to WF-030) testing completeness tracking, convention discovery, security methodology, context utilization, async safety, dead code removal, config extraction, test-driven implementation, structured debugging, and more
- `workspace_claude_md` field in task schema: injects project-level CLAUDE.md into workspaces for tasks that test context discovery
- New capabilities: `completeness_tracking`, `convention_adherence`, `context_discovery`, `security_methodology`
- Benchmark grows from 80 to 100 tasks: workflow category is 30% of total score

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
- Coding-performance hooks now fire in benchmark mode (frustration-detector, stop-continuation, file-count-escalation): these ARE the workflow being measured

### Changed
- Benchmark no longer disables workflow hooks: custom adapter runs with full coding-performance automation while vanilla runs with none, producing a true workflow contribution measurement
- CLAUDE.md execution discipline rules moved to top of file for maximum attention

### Fixed
- Benchmark guard correctly distinguishes ops hooks (skip in unfamiliar repos) from coding hooks (always fire)

## 0.2.0 (2026-03-22)

### Added

- 60-task benchmark suite across 7 categories: bug-fix, feature-addition, refactoring, code-review, debugging, multi-file, legacy-code
- Sigmoid normalization with per-task baselines: scores never go negative, smooth gradient above baseline
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
- Normalization: sigmoid curve replaces linear: cost above baseline no longer collapses score to 0
- Per-task baselines derived from task difficulty instead of global constants
- Difficulty-weighted aggregation: hard=2.5×, medium=1.5×, easy=1.0×

## 0.1.0 (2026-03-20)

### Added

- Initial benchmark harness with 10 tasks
- Claude Code adapters: vanilla and custom variants
- Workflow descriptor system (export, validate, diff)
- Static HTML leaderboard generator
- Linear normalization with global baselines
