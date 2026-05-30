# Security & Isolation

AWB runs real code. Understand the trust boundary before you run it,
especially against task sets or tool configurations you did not author.

## What AWB executes

A single `awb run` does all of the following on your machine, with your user's
privileges:

1. **Clones third-party repositories** at pinned commit SHAs (the task's
   `repo.url` / `repo.commit`).
2. **Runs each task's `setup_commands`** through a shell
   (`asyncio.create_subprocess_shell` in `awb/core/repo_manager.py`) — typically
   `pip install -e .` and friends, which execute arbitrary `setup.py` /
   build-backend code from the cloned repo.
3. **Runs the task's `verification`, `lint`, and `security` commands** through a
   shell against the modified workspace.
4. **Invokes the AI coding tool** against the workspace. The bundled Claude Code
   adapters pass `--dangerously-skip-permissions`, so the agent can read, write,
   and execute inside the workspace without prompts.

There is **no sandbox** between any of this and your host. Task YAML command
strings and cloned repository code are executed as-is.

## The trust boundary

Treat **the task set and the repositories it pins as trusted input**, on the
same footing as code you would `pip install` and run yourself. Concretely:

- The 100 bundled tasks pin specific SHAs of well-known OSS repos. Running them
  executes those repos' build and test code.
- A task YAML's `setup_commands` / `verification` / `lint` / `security` entries
  are shell strings. Anyone who can edit a task YAML can run arbitrary commands
  on a machine that later benchmarks that task.
- `workspace_claude_md` is written verbatim into the workspace's
  `.claude/CLAUDE.md`, so a task can shape the agent-under-test's instructions.
  This is intentional (it is part of what AWB measures) but means a task author
  influences agent behavior.

**Do not run untrusted task sets or third-party submissions on a host you care
about.** AWB does not yet verify or sandbox submitted tasks.

## Recommended precautions today

Until per-task container isolation lands (below), run AWB in a disposable
environment:

- A throwaway VM or container, or a CI runner you can burn.
- A dedicated virtualenv; install AWB with exact-pinned deps (the default).
- Export only the one API key / auth the tool-under-test needs. Avoid running
  with cloud credentials, SSH agents, or production secrets in the environment —
  setup commands and the agent can read them.
- Expect network access: clones and `pip install` reach the internet.
- Trace artifacts (`*.trace.jsonl`) and run logs (`*.log`) can contain file
  paths and shell commands the agent ran. Review before publishing a baseline.

## Scope: Docker isolation (v1.4 target)

Per-task container isolation is the table-stakes feature that makes AWB safe for
community submissions. Target design:

- **One container per task run.** Clone, setup, agent execution, and
  verification all happen inside it; the host only collects the result JSON,
  trace, and logs.
- **Read-only host mounts.** No host filesystem write access; the workspace
  lives on a container-local volume discarded after the run.
- **No host network namespace.** Egress allowlisted to the package index and
  the repo origin where possible; the tool's API endpoint passed explicitly.
- **Resource limits.** CPU, memory, PID, and wall-clock caps per container so a
  runaway setup or agent loop cannot exhaust the host (complements the existing
  per-operation timeouts).
- **No host secrets by default.** Only the tool's API key is injected, as a
  single scoped env var.
- **An `--isolation docker` flag** on `awb run`, defaulting off for local
  development and on for the submission-ingestion path.

This unblocks accepting external submissions (run an untrusted tool config and
task set without trusting either) and is tracked as the lead v1.4 item.

## Reporting

Found a security issue in AWB itself (not in a benchmarked repo)? Open a GitHub
issue or contact the maintainer listed in `pyproject.toml`.
