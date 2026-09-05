# Task review protocol

Task definitions are not added to a holdout just because they load or score a
saved result. Review evidence records what was checked and leaves admission to
a separate human decision.

Start with the static inventory:

```bash
awb task audit --format text
awb task audit --tasks-dir ./candidate-tasks --format json
```

The audit scans every YAML file in the selected directory. It flags shell
partial-credit checks that end in `; true` or `|| true`, definitions without a
provenance mapping, and definitions without current control evidence. Its
`reviewed` count is always zero: it never infers human review or holdout
admission from a task file.

Create a failure candidate only with reviewer-written context and an oracle
note. Supplying the originating task definition preserves its repository and
provenance fields. It records a SHA-256 identity for that exact definition.

```bash
awb task from-failure results/runs/example/BF-901_tool.json \
  --out ./candidate-reviews \
  --description "The agent did not create the required file." \
  --oracle-review "Confirm the file check is independent of the task prompt." \
  --task-definition ./candidate-tasks/BF-901.yaml
```

The command writes a candidate JSON file and a sibling review JSON file. Both
carry `admission: not_admitted`. They are not executable admission requests.

Run controls against explicit local workspaces after reviewing the task's
trusted partial-credit commands. The protocol executes those existing commands
on the host in the three paths supplied by the operator. Treat this command as
local-only evidence for trusted task definitions. Do not use imported or
unreviewed task checks on a host that has credentials or sensitive files.

```bash
awb task controls ./candidate-tasks/BF-901.yaml \
  --gold-workspace ./fixtures/BF-901-gold \
  --noop-workspace ./fixtures/BF-901-noop \
  --mutation-workspace ./fixtures/BF-901-mutation
```

The gold workspace must receive 100 percent. The no-op and mutation workspaces
must receive zero. A failing control produces `review_required`.
Passing controls produce `review_evidence_ready`. It still has
`admission: not_admitted`. The review includes the task hash, workspace hashes,
criterion receipts, evaluator identity, and a tamper-evident receipt hash.
Review those records with the oracle note and provenance before making any
separate decision to add a task to a holdout.
