# AWB Baselines

This directory holds the immutable per-release results AWB publishes
alongside each tagged version. Each file is the output of `awb export`
against a full-suite run.

## File format

`<tool>-<version>-<run-id>.json` containing:

- `awb_version`: the AWB release that produced the run
- `tool`, `tool_version`, `model`: identifying the agent under test
- `task_set_hash`: SHA-256 of the task YAMLs (must match the bundled
  task set in `awb_version` for cross-comparison)
- `runs`: array of per-task `RunResult` records (schema v2)
- `aggregate`: summary statistics (mean composite, capability profile,
  workflow lift if applicable)

## Generating a baseline

```bash
awb run --runs 3 claude-code-custom
awb run --runs 3 claude-code-vanilla
awb export results/runs/<run_id>/ -o results/baselines/claude-code-custom-1.2.0.json
```

## Cross-version comparison

Baselines tagged for the same `task_set_hash` are directly comparable.
`awb compare-submissions` accepts two baseline files and produces a
significance-tested side-by-side report.

## Live leaderboard

Pushing a new baseline file to `main` triggers
`.github/workflows/leaderboard.yml`, which rebuilds the static
HTML leaderboard and deploys to GitHub Pages.
