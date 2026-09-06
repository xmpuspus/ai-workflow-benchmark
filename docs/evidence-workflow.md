# Compare a configuration change with recorded evidence

Start with a free check.

```bash
awb quickstart
awb checkup --static-only --tool codex-cli
```

These commands do not run a model. Quickstart checks authentication only when you add `--check-auth`.

After an explicit benchmark run, open its saved evidence.

```bash
awb report last
awb report last --format json
awb report last --format html --output report.html
```

The report separates patch correctness from execution status. It shows missing security, lint, regression, and cost evidence. Unknown evidence does not mean a clean result. Old results stay readable, but missing identity fields can prevent comparison.

## Freeze the question before the results

Use one candidate change, such as a shorter instruction file. Keep the model, task definitions, budget, and safety policy the same in both arms. Do not remove permission rules to create a baseline.

A plan specification has these fields.

| Field | Meaning |
|---|---|
| `tool`, `model` | Explicit adapter and model identities |
| `config_a_hash`, `config_b_hash` | Configuration identities for baseline and candidate |
| `safety_policy_hash_a`, `safety_policy_hash_b` | Equal safety-policy identities |
| `task_hashes` | Task ID to SHA-256 definition identity |
| `development_tasks`, `holdout_tasks` | Separate task lists |
| `repeats`, `seed` | Attempt count and reproducible ordering seed |
| `timeout_seconds` | Same agent deadline in both arms |
| `setup_timeout_seconds`, `verification_timeout_seconds` | Stage deadlines |
| `attempt_timeout_seconds` | Combined deadline for one attempt |
| `allowed_env` | Explicit environment variable names passed to the adapter. AWB does not record values |
| `minimum_delta` | Smallest useful score change, set before execution |
| `state_policy` | `fresh_process_per_attempt` |

```bash
awb experiment snapshot ./baseline-config
awb experiment snapshot ./candidate-config
awb experiment plan specification.json --out plan.json
awb experiment verify-plan plan.json
```

The plan counterbalances arm order across repeats. Its hash detects later edits. It does not prove that the configuration is safe or that a task oracle is valid. It records an agent-time bound and a separate sum of per-try deadlines covering preparation, execution, and verification. It does not claim a hard monetary cap.

Controlled execution currently supports `claude-code-custom` and instruction-file changes. Supply dedicated configuration directories containing only these permitted root files. `CLAUDE.md`, `AGENTS.md`, `AGENTS.override.md`, `settings.json`, and `hooks.json`. Both arms must have the same settings and hooks. Skills, nested configuration trees, and Codex controlled execution are outside this command’s supported inputs. The existing `awb ab` remains an exploratory comparison path.

```bash
awb experiment run plan.json --config-a ./baseline-config --config-b ./candidate-config \
  --tasks-dir ./reviewed-tasks --split development --runs-dir ./experiment-results
```

This command calls the model. Each try uses a fresh process and vetted configuration copy. AWB pins the requested model, checks the model reported by the tool, and stops on failed execution. It reuses completed receipts. An interrupted try with uncertain completion needs review.

Each adapter try receives private home, temporary, and XDG state directories. AWB forwards `PATH` and the names explicitly declared in `allowed_env`. Authentication needs an explicitly allowed API credential variable. AWB does not copy existing login files.

Setup and verification run as trusted host code. This command does not use the offline Docker boundary. Read [the execution boundaries](SECURITY.md).

Holdout execution needs a qualifying development decision and current positive and negative task-control receipts, and a separate task admission declaration. Reusing the same candidate/model/holdout under a different plan is rejected within the same results directory. Preserve that directory. This local guard cannot prevent an operator from deleting records or using another machine.

Use development tasks to choose a candidate. Freeze that candidate before one confirmation experiment on the holdout. Do not select a new candidate from holdout failures and describe a rerun as independent confirmation.

```bash
awb experiment assess plan.json baseline-attempts.json candidate-attempts.json --split development
awb experiment assess-run plan.json --runs-dir ./experiment-results \
  --tasks-dir ./reviewed-tasks --split holdout
```

Imported holdout arrays always stay inconclusive. `assess-run` checks the local run store, development evidence, frozen task bytes, task controls, and holdout consumption record. These checks confirm local consistency. They do not authenticate an independent execution or reviewer.

Assessment needs matching plan receipts and complete repeated tries. Missing receipts, model changes, task changes, or missing pairs give an inconclusive result. The plan assessment uses the median within each task. It reports repeat variance, paired task deltas, and cost per solved try. The cost includes failed tries and stays unknown if usage or schedule coverage is incomplete. Fewer than five paired tasks support descriptive results only.

The task is the pairing unit. Several tasks from one repository are related evidence. A sign test across selected tasks does not show an effect across all repositories or human developers. Practical thresholds and statistical evidence answer different questions.

## Keep enough evidence to check the result

```bash
awb experiment bundle results/runs/RUN_ID --out evidence-bundle
awb experiment verify-bundle evidence-bundle
```

The default bundle copies nested task result JSON and declared `plan.json`, `evaluator.json`, and `environment.json` metadata when present. Missing replay metadata is marked incomplete. Add traces or patches explicitly with repeatable `--attach PATH` options. It does not copy authentication files or ambient directories.

Result fields can still contain private paths, error text, or metadata. Inspect the bundle before sharing it. Checksums detect changed files. They cannot validate the measurements.

Keep the exact task definitions and permitted configuration files available for replay. The bundle does not collect arbitrary source trees. Place declared metadata at the result directory root before export. A reader must distinguish a missing artifact from a measured absence.

## Review tasks before confirmation

```bash
awb task audit --format json
awb task controls tasks/BF-901.yaml --gold-workspace gold --noop-workspace noop \
  --mutation-workspace mutation --format json
```

The audit reports gaps for every task. The control command tests explicit local workspaces and writes a hash-bound review record. It does not admit the task to a holdout. Read [the task review process](task-review.md) before accepting a candidate.

The bundled suite remains a development suite. Its historical tasks do not become independently reviewed through a schema update. Public task prompts can be contaminated. Do not treat a new collection date as proof of low contamination.

## Measure adoption with real participants

Before a broad usefulness claim, ask five representative users to run the free path on their own setup. Give them no guided tour. Ask each person to explain what ran, what remains unknown, and the next action within five minutes. Record the exact task, elapsed time, errors, and assistance. The target is at least four successful users.

Ask two people outside the implementation effort to replay an experiment from its manifest in clean environments. Record tool and model versions, environment identity, the commands used, discrepancies, and the final evidence. A developer running a second local environment is useful verification, but it does not meet this independent-adoption gate.

Track the first useful report, completed experiments, candidate decisions, confirmation rate, and later repeat use. Use opt-in local records. Do not infer demand, retention, or productivity from test counts or scheduled runs.

## Evidence behind this workflow

Paired evaluation and within-task repeats reduce avoidable comparison noise. See [Anthropic's evaluation statistics](https://www.anthropic.com/research/statistical-approach-to-model-evals).

Configuration changes can add cost without helping task success. This makes instruction reduction a useful candidate experiment. See [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988).

Task quality needs positive and negative controls. An oracle that accepts a meaningless patch cannot support a tool comparison. See [OpenAI's coding-evaluation audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/).

Execution isolation must include setup and verification as well as the agent. See [Inspect's sandbox interface](https://inspect.aisi.org.uk/sandboxing.html) and [Harbor's oracle workflow](https://www.harborframework.com/docs/tutorials/running-terminal-bench).
