# Local evidence workflow implementation

The local implementation addresses the product audit's measurement, execution, reporting, and experiment-control findings. It keeps the existing CLI and readable legacy results. It does not measure human productivity, market demand, or a validated improvement from any particular model configuration.

The tested code checkpoint is `15a0d75` on `improve-evidence-workflow`. The implementation uses an isolated worktree. Nothing was pushed, published, deployed, or sent to an external recipient.

## Missing evidence no longer earns a perfect score

Repeated observations are aggregated within each task. Unequal repeat coverage makes a paired comparison inconclusive. Empty traces, missing scans, and incomplete usage stay unmeasured. The results keep baseline and post-change security counts, so zero new issues cannot hide pre-existing findings.

Comparison eligibility needs a complete task-repeat grid and matching tool, model, configuration, evaluator, environment, budget, and task identities. The evaluator identity includes a fingerprint of its packaged Python source. Unknown legacy identity keeps results visible but unranked. Sorting the leaderboard cannot manufacture ranks. CSV exports preserve identity and leave unknown costs empty.

BF-001, BF-009, and CR-007 now use behavioral oracles. Their tests reject the reproduced trivial or unconditional solutions and check known-good implementations. Four scanner commands no longer suppress their failures.

## Free entry points lead to saved evidence

`awb quickstart` skips authentication unless requested. CLI help groups the next actions. `awb report` reads saved evidence in text, JSON, and standalone HTML without an adapter or model call. Reports distinguish patch correctness from execution status and show missing measurements, task details, trace references, and a command to preview another try.

The leaderboard supports text sorting, filtering, and CSV download on desktop and mobile. Mobile tables keep their columns and show a horizontal-scroll cue.

## Interrupted execution preserves its evidence

Results record execution stage, termination, tool exit status, usage completeness, and input/environment manifests. Resume checks current identity before reusing receipts. Once the deadline expires, sequential and queued parallel tasks stay unstarted and can be resumed. Timeout and cancellation checks cover subprocess groups.

`awb run --container-image IMAGE` puts setup, adapter execution, verification, and persistence inside an offline Docker invocation. It uses an immutable image identity, resource limits, narrow mounts, and no ambient credentials. This supports prepared offline images. It does not support authenticated network access or one container per task.

## Confirmation needs a frozen plan and separate admission

`awb experiment` adds configuration snapshots, predeclared plans, counterbalanced repeats, explicit deadlines, local execution, assessment, and portable evidence bundles. Controlled execution currently supports instruction-file changes through `claude-code-custom`. Settings and hooks must match across arms. Each adapter try gets fresh private state directories and explicitly allowed environment variables.

Imported holdout arrays stay inconclusive. `assess-run` checks local task bytes, development receipts, control reviews, separate admission declarations, and the holdout-consumption record. These checks detect inconsistencies within the local record. They are not independent attestation. A user who deletes or forges their own records can defeat a local history policy.

Task candidates stay unadmitted. Positive and negative controls cannot replace the separate admission decision. Evidence-bundle verification rejects changed, missing, undeclared, malformed, and symlinked artifacts. Checksums do not prove that an oracle is scientifically valid.

## Verification passed on the current code

| Check | Observed result | Local evidence |
|---|---|---|
| Full suite with real Docker control and runtime warnings treated as errors | 822 passed. zero skipped. zero warnings | [Test log](../../tmp/final-suite.log) |
| Ruff and task schema validation | Passed. 100/100 task definitions valid | [Task validation](../../tmp/final-task-validation.log) |
| Fresh wheel build and isolated installation | Commands succeeded and imported the installed wheel. evaluator source fingerprint matched | [Installation checks](../../tmp/wheel-smoke/checks.json) |
| Free static check and saved report | JSON parsed. saved report showed 8 results, 4 passed, 4 failed, missing evidence, and ineligible comparison | [Report payload](../../tmp/final-visual/report.json) |
| Desktop/mobile interactions | Sorting, filtering, CSV download, preserved ranks and identity, no page overflow or JavaScript errors | [Browser checks](../../tmp/final-visual/checks.json) |
| Visual inspection | Read report and leaderboard screenshots at 1920x1080 and 375px. controls remained readable | [Report preview](../../tmp/final-visual/report.html), [leaderboard fixture](../../tmp/final-visual/leaderboard/index.html) |
| Real container controls | Correct arithmetic scored 100. no-op scored 0 | Full suite's `test_container_integration.py` |
| Installed CLI evidence bundle | Nested receipts exported. valid bundle passed. tampered bundle failed. malformed manifest returned JSON error and exit 2 | [Wheel command checks](../../tmp/wheel-smoke/checks.json) |

The Docker controls and synthetic leaderboard rows test software behavior. They are not model benchmark results. The saved eight-task report is historical evidence re-rendered with the new reader.

## Broader claims still need external evidence

The five-user usability study and two independent experiment replays have protocols but no completed participants. The bundled public corpus stays a development corpus until individual tasks receive independent oracle, provenance, contamination, and admission review. This work did not confirm a configuration improvement on a representative holdout.

Controlled Codex experiments, skill/hook ablations, authenticated container networking, per-task containers, hosted services, marketplaces, and public releases are outside the implemented scope. Host experiment and task-control commands still need trusted code. See [execution boundaries](../SECURITY.md), [task review](../task-review.md), and the [configuration comparison guide](../evidence-workflow.md).

## The original checkout's source was preserved

One worker accidentally committed in the original checkout and then reverted its commit before the stop instruction arrived. Its source content was restored. Original local `main` keeps accidental commit `fcacf58` and revert `5f158cf`. its history was not rewritten. Pre-existing instruction-file changes and untracked artifacts stay intact. The enhancement implementation lives on the isolated branch.
