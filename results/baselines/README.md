# AWB Baselines

This directory holds the immutable per-release results AWB publishes
alongside each tagged version. Each file is the output of `awb export`
against a full-suite run.

## File format

`<tool>-<awb_version>-<scope>.json` (where `scope` is `full` or
`fast-check`) emitted by `awb export`:

```jsonc
{
  "spec_version": "awb/v2",
  "submission": {
    "submitter": "anonymous",
    "submitted_at": "2026-05-24T01:54:23Z",
    "tool":    { "name": "claude-code-custom", "version": "..." },
    "model":   { "name": "..." },
    "environment": {
      "os": "Darwin 25.5.0",
      "hardware_class": "other",
      "hardware_detail": "Apple M5, 24GB"
    },
    "awb_version": "1.3.0"
  },
  "results": [
    { "task_id": "BF-001", "runs": [ ... per-run RunResult records ... ] },
    ...
  ]
}
```

The `submission.awb_version` field is what gates cross-baseline
comparison: two baselines built against the same `awb_version` carry
the same `task_set_hash` and are directly comparable.

## Generating a baseline

```bash
# Fast-check baseline (8 representative tasks, 1 run, ~15 min, ~$4)
awb run --fast-check claude-code-custom
awb export results/runs/<run_id>/ \
  -o results/baselines/claude-code-custom-1.3.0-fast-check.json

# Full-suite baseline (100 tasks, 3 runs each, ~3 hrs, ~$150)
awb run --runs 3 claude-code-custom
awb run --runs 3 claude-code-vanilla
awb export results/runs/<run_id>/ \
  -o results/baselines/claude-code-custom-1.3.0-full.json
```

## Cross-version comparison

Baselines tagged for the same `task_set_hash` are directly comparable.
`awb compare-submissions` accepts two baseline files and produces a
significance-tested side-by-side report.

## Live leaderboard

Pushing a new baseline file to `main` triggers
`.github/workflows/leaderboard.yml`, which rebuilds the static
HTML leaderboard and deploys to GitHub Pages.
