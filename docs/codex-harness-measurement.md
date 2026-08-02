# Codex harness measurement

Measured on 2026-08-02 with the AWB 1.7.0 release candidate.

## Harness inventory

- Tool: `codex-cli 0.146.0-alpha.9.2`
- Model: `gpt-5.6-sol`
- Reasoning effort: `xhigh`
- Service tier: standard
- Workflow config hash: `e3be57133e6300bd`
- Global AGENTS hash: `b7fcbcd331a08e3c`
- Hooks: 14
- Custom agents: 15
- Skills: 112
- Rules files: 2
- Plugins: 21
- Structural issues: 0
- Recognized testable promises: 5
- Unparsed rules and hook declarations: 40

Inventory counts describe installed harness artifacts, not proof that every
artifact was selected or invoked during each task.

## Eight-task checkup result

Recorded run ID: `2026-08-02_002909_run1`

- Passed: 4/8 tasks (50%)
- Full score: BF-001, DB-001, LC-001, WF-001
- Partial score: MF-001 at 25/100
- Completed failure: RF-001 at 0/100
- Timed out: CR-001 and FA-001
- End-to-end elapsed time: 32 minutes
- Sum of task execution time: 1,741.9 seconds

| Task | Result | Score | Seconds | Credits | Files | Lines |
|---|---:|---:|---:|---:|---:|---:|
| BF-001 | pass | 100/100 | 194.6 | 16.3398 | 1 | 64 |
| CR-001 | timeout | 0/0 | 323.0 | unavailable | unavailable | unavailable |
| DB-001 | pass | 100/100 | 285.6 | 24.3483 | 4 | 21 |
| FA-001 | timeout | 0/0 | 231.0 | unavailable | unavailable | unavailable |
| LC-001 | pass | 100/100 | 184.9 | 15.9241 | 2 | 56 |
| MF-001 | fail | 25/100 | 215.6 | 18.0529 | 0 | 0 |
| RF-001 | fail | 0/100 | 97.0 | 10.7465 | 0 | 0 |
| WF-001 | pass | 100/100 | 210.2 | 16.3283 | 1 | 25 |

The timeout file counts above are unavailable in this recorded run. The run
exposed that AWB cleaned partial timeout patches before measuring them. The
runner was fixed afterward and a dedicated timeout test now proves partial
patch counts survive cleanup.

## Harness behavior scores

- Verification discipline: 100.0
- Scope discipline: 97.9
- Efficiency: 83.6
- Rule integrity: 2/4 testable rules held, 2 broken, 1 untested

Held:

- Scope constraints held in 8/8 tasks.
- Verification-before-completion held in 8/8 tasks.

Broken:

- Codex violated the global read-tests-before-edit promise in 3/8 tasks.
- Codex violated the repository read-tests-before-edit promise in the same 3/8
  tasks: DB-001, FA-001, and LC-001.

Untested:

- Commit hygiene has no observable trace rubric yet.

## Usage and cost lower bound

- Completed-turn input tokens: 2,952,561
- Cached input tokens: 2,621,696
- Output tokens: 36,814
- Reasoning output tokens: 19,618
- Recorded tool calls: 124
- Native credits: 101.7399
- Dollar-equivalent estimate: $4.0696
- Credits per solved task: 25.4350
- Dollar-equivalent cost per solved task: $1.0174

The usage total excludes CR-001 and FA-001 because AWB stopped Codex at the
task timeout before emitting `turn.completed.usage`. The credit and token
totals are lower bounds, not complete spend.

## Main finding

The harness is strong at verification and scope control once Codex completes a
turn. Its limiting factor in this probe is execution reliability under AWB's
task budgets: two of eight tasks timed out, and two more completed without a
correct solution. The clearest harness-level correction is to make
read-tests-before-edit mechanically observable or enforced, then retest with a
lower reasoning effort or larger task-specific timeouts as a separate A/B.
