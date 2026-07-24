# AWB v1.6 design: grade the harness, prove the rules fired, in under five minutes

Research-backed design for making AWB the tool that measures how well someone designed their
AI coding harness (CLAUDE.md, rules, hooks, skills, permissions, workflow). Four research
streams feed this doc; full evidence with sources in
`tmp/harness-research-20260724T023327Z/` (01 harness-design taxonomy, 02 benchmark-tool UX
patterns, 03 practitioner demand signals, 04 AWB codebase fit audit). Load-bearing claims
were spot-verified against primary sources and AWB source code before landing here.

## The four findings that force this design

**1. The static-linter market is crowded, and it is optimizing properties with null evidence.**
Seven active CLAUDE.md/AGENTS.md linters exist (agnix 363 stars with 437 rules, agentlinter,
ctxlint, claudelint, two cclints, ccmd.dev). All score the config file's text: token counts,
contradictions, schema validity. The one controlled factorial study on record (arXiv
2605.10039, 1,650 Claude Code sessions, 16,050 observations) found file size and
adjacent-file contradictions have NO detectable effect on instruction adherence, with
affirmative-null Bayes factors 0.05-0.10. A static AWB linter would enter a commodity space
late, to score properties the evidence says do not predict outcomes.

**2. The behavioral levers are where the measured effects live, and AWB already owns the
machinery.** Verification-gate tuning of guidance files lifted SWE-bench Verified resolve
from 25.5% to 33.0% (arXiv 2606.20512). Within-session compliance decays 5.6% per additional
function generated (arXiv 2605.10039), a purely dynamic property no file read can see.
Specific instructions are followed while generic repo overviews measure as inert (arXiv
2602.11988). AWB's deterministic trace rubrics, paired sign test, and Workflow Lift are
exactly the instruments these effects require. Exactly one competitor does behavioral
before/after harness scoring: ai-harness-doctor, 3 stars, 2 weeks old, one demo repo, no
statistical test, and its own README disclaims universality.

**3. The most-demanded unshipped feature is proof that a rule actually fired.**
anthropics/claude-code#80579 (527 issues match "CLAUDE.md ignored"; four closed duplicates
spanning a year) diagnoses it: "rules are declarative context, generative output is not
gated by that context." #79948: "when the agent controls the enforcement, enforcement is
voluntary." ccmd.dev lists "session-trace analysis to see which rules actually fire" as
unshipped roadmap. Nobody ships this. AWB's traces already contain the evidence.

**4. Speed and comprehension are the adoption gates, and both have concrete defects today.**
Verified in source this session: `awb run --fast-check` with no tool name silently drops the
flag (`_run_both` at `awb/commands/run.py:24-37` takes no `fast_check` parameter; the
tool-less branch at `run.py:262-278` never forwards it) and runs 600 task executions instead
of 8, roughly $300 instead of $4. Fast-check runs its 8 tasks sequentially by default.
Onboarding is 4-6 commands, run directories are hand-copied between commands, and no output
anywhere states a top-line verdict. Lighthouse's UX research (02) says the winning pattern
is one headline number per category, recommendations pre-sorted by estimated impact, and a
published, explainable scoring curve.

## The product: `awb checkup`, one command, three stages

One command a first-time user can run with zero arguments from any repo. Auto-detects the
harness (`~/.claude` and/or repo-level CLAUDE.md/AGENTS.md/.cursor/rules), never asks for an
adapter name, prints signal in escalating stages so the user gets value at 5 seconds, not
only at minute 15.

```
awb checkup                  # stage 0 free + stage 1 probe (8 tasks, parallel, ~$2-4)
awb checkup --static-only    # stage 0 only, zero spend, CI-safe
awb checkup --paired         # adds vanilla arm for Workflow Lift (2x probe cost)
```

**Stage 0, instant and free: promise extraction, not a quality score.** Parse the harness
files and (a) sanity-check structure: hook script paths in settings.json resolve, JSON
parses, referenced files exist, documented commands match the repo's actual build files
(package.json, pyproject.toml); (b) extract the harness's testable promises: verification
gates ("run tests before done"), scope rules ("never touch X", "minimal fix"), read-before-
edit rules, lint gates, and classify each rule as hook-enforced (deterministic) or
prose-only (advisory). Output: the promise inventory plus structural defects. Deliberately
NOT a 0-100 static quality score: the null-result study makes scoring text properties as
quality indefensible, and stating that in the docs is a trust argument no linter can copy.

**Stage 1, the probe: 8 tasks, parallel, one run each, ~3-5 minutes warm.** Fast-check's
existing task selection, after the P0 fixes (bug fix, parallel default at -j 4, auth
preflight before any clone). Traces graded on 6 rubrics (4 existing + 2 new that need no
translator changes, per audit: `context_discipline` = distinct files read vs
files_to_examine; `tool_call_efficiency` = duplicate read/edit thrash). `--paired` runs the
vanilla arm too and reports Workflow Lift with the sign test.

**Stage 2, the report: verdict first, evidence attached, fixes ranked.**

```
Harness Design Report            claude-code-custom, 8/100 tasks, confidence: low
Verdict: your harness verifies its work (100) but breaks its own scope rule
in 3 of 8 tasks, and 2 of 7 stated rules never demonstrably fired.

  Verification discipline   ████████░░  92   ran checks after every change
  Scope discipline          ████░░░░░░  41   out-of-scope edits in 3/8 tasks
  Efficiency                ██████░░░░  64   2.1x re-reads of same files
  Rule integrity            █████░░░░░  5/7  2 rules untested by these tasks

Top fixes (estimated impact, independent estimates, not additive):
  1. +12 pts  Scope rule is prose-only and was violated 3x. Convert to a
              PreToolUse hook. [snippet ready: awb checkup --apply]
  2.  +6 pts  No lint gate stated or observed. Add one command: ...
```

## The signature feature: the rule-integrity table (promises vs behavior)

Stage 0 extracts what the harness claims; stage 1 traces prove what happened. Join them:

| Rule (from CLAUDE.md/hooks) | Enforcement | Observed in 8 tasks | Verdict |
|---|---|---|---|
| "run tests before declaring done" | prose | fired 8/8 | HELD |
| "never edit files outside scope" | prose | violated 3/8 | BROKEN |
| "read tests before editing" | prose | fired 6/6 applicable | HELD |
| "use ruff before commit" | hook | hook present, fired | ENFORCED |
| "keep PRs under 300 lines" | prose | no applicable task | UNTESTED |

This is demand-signal whitespace #2, verbatim what #80579 and #79948 ask for, listed as
future roadmap by the closest competitor product, and derivable from artifacts AWB already
writes. Deterministic (pattern-match rule extraction + existing span grading), no LLM judge.
The escalation recommendation writes itself and matches Anthropic's own design guidance
(hooks are deterministic, CLAUDE.md is advisory): a BROKEN prose rule gets a ready-to-paste
hook; an UNTESTED rule gets the task category that would exercise it.

Rule extraction starts narrow and honest: a fixed taxonomy of maybe 8 checkable rule
patterns (verification gate, scope constraint, read-before-edit, lint gate, test-first,
commit hygiene, file-count budget, forbidden-path), pattern-matched with a visible list of
what was NOT parseable. Unrecognized rules are listed as "not checkable yet", never
silently dropped. Precision over recall; a wrong HELD/BROKEN verdict costs all trust.

## Scoring: Lighthouse's honesty rules applied to AWB's existing math

- **Pillars, not one opaque blob.** Verification discipline, scope discipline, efficiency
  (each from trace rubrics + token/cost telemetry), rule integrity (ratio, shown as n/m not
  0-100), and, only when `--paired` ran, outcome lift (Workflow Lift + p-value). A missing
  pillar is labeled "not measured", never imputed (Artificial Analysis pattern: exclude
  missing telemetry, never zero it).
- **Anchored, published curve.** Sigmoid control points derived from the published baselines'
  empirical percentiles instead of hand-picked constants (extend `awb calibrate-difficulty`
  to emit them). `awb score explain` recomputes any composite from its inputs, the
  scorecalc pattern.
- **Confidence is loud.** 8 tasks is "confidence: low" in the header, with the existing
  fast-check 95% CI on the full-suite estimate. Impact estimates on fixes carry the
  Lighthouse caveat in the output itself: independent estimates, do not sum.
- **Uniform exit codes for CI:** 0 clean, 1 finding past threshold, 2 tool failure, across
  checkup/drift/ab/validate, documented once in `_shared.py`.

## Recommendations engine: extend prescriptions, add impact ranking and --apply

- Cover all 11 capabilities (today 4 of 11 have prescription entries; the worst-scoring
  capability can currently fail silently, `awb/analysis/prescriptions.py:114-177`).
- Attach `estimated_score_delta` per prescription (historical score gap of that rubric),
  sort descending, print the non-additivity caveat.
- ruff's safety split: `--apply` writes only `safe`-tagged CLAUDE.md snippets (append-only,
  clearly fenced), prints `needs-review` ones. Hook prescriptions are always needs-review.
- The rule-integrity escalation above becomes a prescription source alongside rubric and
  capability failures.

## Speed: the floor is minutes today and the fixes are small

| Fix | Effort | Effect |
|---|---|---|
| Wire `--fast-check`/`--progressive`/`--yes` into `_run_both` or refuse the combo | S | kills the silent $300 path (P0 bug) |
| Fast-check defaults to parallel, -j 4 | S | ~15 min to ~3-5 min |
| Auth preflight in `_run_both` before cloning | S | fail in 1s, not after a clone |
| `awb warmup --fast-check` (warm only the 8 probe repos) | S | one-time setup ~5 min to ~1-2 min |
| Result cache keyed (adapter, config_hash, task_id, repo_sha) | M | unchanged arms in ab/drift skip re-runs |
| `--last-run` accepted by gap/cost/trace/drift/checkup | S | no hand-copied run dirs |

Target: cold install to first full report under 10 minutes; warm iteration loop (edit
CLAUDE.md, re-checkup) under 5 minutes and ~$2-4. That loop speed is what makes the tool an
instrument instead of a ceremony.

## Trust hardening: assume the agent attacks the scorer

UC Berkeley's exploit agent compromised all 8 major agent benchmarks it tested (100% scores,
zero tasks solved), largely via test tampering such as a conftest.py that force-passes
everything. AWB's answer, cheap and stated in METHODOLOGY.md: before verification, re-
checkout test files from the pinned SHA and hash-compare; verification runs outside the
agent's workspace process; any mismatch scores the task 0 with a TAMPERED flag. No config
linter and neither behavioral competitor makes this argument today.

## Positioning: behavior-graded, statistically paired, on your own repos

README lead stays an instrument, not a leaderboard (v1.5 strategy holds). The one-table
pitch: linters read your config's text (and the only controlled study found those text
properties don't predict adherence); ai-harness-doctor runs one demo repo with no stats; AWB
extracts your harness's own promises, runs real tasks, proves which rules held, and pairs
every score with cost. Cite 2605.10039, 2602.11988, 2606.20512 in METHODOLOGY related work.

## What NOT to build (scope discipline)

- No 437-rule static linter arms race; stage 0 checks structure and extracts promises, and
  its README section says why it refuses to score text (the null result), which converts a
  gap into a differentiator.
- No LLM-judge rubrics; determinism is the trust story (v1.2 decision reaffirmed by the
  Berkeley findings).
- No public harness-score leaderboard; private instrument positioning.
- No new scoring math where existing math can be re-surfaced (Workflow Lift, readiness,
  rubric means already exist; checkup composes them).

## Release slices

**v1.5.5 (patch, ship first):** fast-check wiring bug + auth preflight in `_run_both` +
fast-check parallel default. The bug actively burns money on the most natural command line a
new user would type.

**v1.6.0 (the checkup release):** `awb checkup` (stage 0 promise extraction + stage 1 probe
+ verdict report), 2 new trace rubrics, rule-integrity table v1 (8 rule patterns), verdict
line also added to `awb gap`, `--last-run` plumbing, prescriptions coverage to 11
capabilities + impact ranking, exit-code contract, `awb warmup --fast-check`.

**v1.7.0 (trust + polish):** `--apply` with safety tiers, result caching, tamper-guard +
METHODOLOGY security section, `awb score explain`, calibrated curve control points from
baselines, README repositioning + fresh hero/checkup GIF (real vhs recording per demo
discipline), paired-mode UX color pass on ab output (regression rows in BAD, improvements in
OK).

Open items deliberately deferred: parsing .cursor/rules and AGENTS.md variants beyond
promise extraction (cross-tool adapters can reuse the same rule taxonomy later); plan-
before-edit rubric (needs translator work to see TodoWrite/plan tool calls; audit says
materially larger); any static contradiction/length scoring (evidence-null).
