# Execution boundaries

AWB executes repository setup, task verification, and coding-tool commands. Choose the boundary explicitly before running those inputs.

## Host runs need trusted code

The default `awb run`, `awb ab`, `awb experiment run`, and `awb task controls` execute on the host. Repository build scripts and task YAML shell commands have the operator's permissions. A pinned commit records identity. It does not make the code safe.

Ordinary Claude adapters use unattended permission flags. The controlled experiment executor removes the permission-bypass flag, needs equal settings and hooks in both arms, and supplies a fresh configuration copy per try. Each adapter try has private home, temporary, and XDG state directories. AWB forwards `PATH`, execution markers, and explicitly allowed variable names. API credentials need an explicitly allowed variable. AWB does not copy login files.

This filters environment inheritance. It is not filesystem isolation. Setup and verification still run as trusted host code.

Use dedicated credentials and a disposable environment for benchmark execution. Do not run imported tasks or configurations on a host containing sensitive files. AWB does not admit community tasks merely because their schema or controls pass.

## Offline Docker runs isolate the complete benchmark process

```bash
awb run codex-cli --task WF-999 --tasks-dir ./prepared-tasks --runs 1 \
  --container-image YOUR_PREPARED_IMAGE --experiment-timeout 300 --yes
```

The image must contain the adapter executable and dependencies. Repositories and setup inputs must be available offline. The launcher resolves the image to its immutable Docker identity and records it with the results.

The container uses no network, a read-only root filesystem, a temporary workspace, and CPU, memory, process, and wall-time limits. AWB source and explicit task/workflow inputs are mounted read-only. The designated results directory is writable. The launcher does not forward the host environment or mount the host home. It removes its own container on timeout.

The boundary covers setup, adapter execution, verification, and persistence in one container per `awb run` invocation. Tasks in that invocation share the container. This is not per-task isolation, authenticated cloud access, or an egress allowlist. The launcher supplies neither a Docker socket nor credentials. It is not a guarantee against a container-runtime vulnerability.

The repository's optional container integration test uses a deterministic adapter subprocess. Correct code earns 100 and a no-op earns 0. That checks the local execution path. Model performance and readiness to accept untrusted community submissions need separate evidence.

## Plans and receipts record local evidence

Plans freeze inputs, order, repeats, and deadlines. Receipt validation rejects missing or incompatible evidence. Holdout consumption records operate within the selected results directory. An operator who changes or deletes that directory can bypass the local history. Checksums detect edits. They do not authenticate an independent reviewer.

Evidence bundles include result fields, declared metadata, and explicitly selected attachments. These may contain private paths, task text, or command output. Review them before sharing. The exporter does not collect authentication or session directories.

## Report a vulnerability

For an AWB vulnerability, contact the maintainer listed in `pyproject.toml`. Avoid including credentials or private benchmark content in a public report.
