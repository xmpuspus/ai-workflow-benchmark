---
license: mit
task_categories:
  - text-generation
language:
  - en
tags:
  - code
  - benchmark
  - llm-evaluation
  - coding-agents
  - software-engineering
  - claude-code
pretty_name: AI Workflow Benchmark (AWB) Tasks
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files: data/tasks.jsonl
---

# AI Workflow Benchmark (AWB) — Task Set

The 100 task definitions from [AI Workflow Benchmark (AWB)](https://github.com/xmpuspus/ai-workflow-benchmark),
a harness that scores the full AI coding stack — tool + configuration + workflow + model — on
multi-step software engineering work against pinned real-world repositories.

This dataset is the **task corpus only**: the problem statements, verification specs, constraints,
and metadata that AWB runs an assistant against. It does not contain model outputs or scores. Run the
[`awb`](https://pypi.org/project/awb/) CLI to produce results.

## Honest provenance (read this first)

All 100 tasks are labelled `synthetic_overlay` with `contamination_risk: high`. They are **authored
problem statements overlaid on 5 real, permissively-licensed Python repositories at pinned commit
SHAs** — not harvested from real merged pull requests. The repos (FastAPI, Flask, Click, httpx,
Starlette) are widely present in pretraining corpora, so a model may have seen the surrounding code.
Treat scores as a measure of workflow discipline on realistic-but-known code, **not** as a
contamination-free capability benchmark. AWB's `provenance`, `contamination_risk`, and `label` fields
exist precisely so this is auditable; the `real_pr` / `mutated` / `fresh` labels are reserved for
future fresh-task harvesting and are not used here.

## What's in each row

| Field | Type | Notes |
|---|---|---|
| `id` | string | e.g. `BF-001`, `WF-014` |
| `category` | string | one of: bug-fix, feature-addition, refactoring, code-review, debugging, multi-file, legacy-code, workflow |
| `title` | string | one-line task summary |
| `difficulty` | string | easy / medium / hard |
| `estimated_minutes` | int | human time estimate |
| `languages` | list[string] | all `["python"]` in this release |
| `issue` | string | the problem statement given to the assistant |
| `repo_url`, `repo_commit`, `repo_setup` | string | pinned target repo + setup command |
| `tests` | list[string] | verification commands |
| `partial_credit` | JSON string | scoring rubric (points sum to 100 per task) |
| `constraints` | JSON string | e.g. `max_files_changed`, `must_pass_existing_tests` |
| `tags`, `capabilities` | list[string] | optional metadata |
| `label` | string | `synthetic_overlay` for all rows |
| `contamination_risk` | string | `high` for all rows |
| `provenance_*` | string | source PR (null here), created/verified dates |
| `has_workspace_claude_md` | bool | whether the task ships a workspace CLAUDE.md |

`partial_credit` and `constraints` are stored as JSON strings so the schema stays flat and typed; parse
them with `json.loads`.

## Composition

- **100 tasks** across **8 categories**: workflow (30), bug-fix (12), legacy-code (12), refactoring (11),
  debugging (10), code-review (9), feature-addition (9), multi-file (7).
- **Difficulty**: easy 21, medium 45, hard 34.
- **Languages**: Python (100).
- **Target repos**: FastAPI (30), httpx (21), Flask (19), Click (18), Starlette (12).

Full distributions and the canonical task-set hash are in [`stats.json`](stats.json).

## Usage

```python
from datasets import load_dataset

ds = load_dataset("xmpuspus/awb-tasks", split="train")
print(ds[0]["id"], ds[0]["category"], ds[0]["title"])

import json
rubric = json.loads(ds[0]["partial_credit"])
```

To actually run the benchmark:

```bash
pip install awb
awb run --fast-check claude-code-custom
```

## Versioning

This snapshot tracks the task set bundled with the AWB release noted in `stats.json` (`task_set_hash`).
Regenerate from the source repo with `python3 scripts/build_hf_dataset.py`.

## Citation

```bibtex
@software{puspus_awb,
  author  = {Puspus, Xavier},
  title   = {AI Workflow Benchmark (AWB)},
  url      = {https://github.com/xmpuspus/ai-workflow-benchmark},
  doi      = {10.5281/zenodo.20361437}
}
```

## License

MIT, matching the AWB source repository. The target repositories retain their own licenses.
