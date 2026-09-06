from __future__ import annotations

import asyncio
import contextlib
import difflib
import hashlib
import logging
import shutil
from pathlib import Path

from awb.core.config import TaskDefinition
from awb.core.subprocesses import run_exec, run_shell

log = logging.getLogger(__name__)

_CLONE_MAX_RETRIES = 3
_CLONE_BACKOFF_BASE = 5  # seconds
_CACHE_DIR = Path.home() / ".cache" / "awb" / "clones"
_TEMPLATE_DIR = Path.home() / ".cache" / "awb" / "templates"


def _setup_cache_key(url: str, commit: str, setup_commands: list[str]) -> str:
    """Hash a (url, commit, setup_commands) tuple for the workspace template cache.

    Order of setup_commands participates in the hash because install order is
    semantically meaningful (e.g., installing requirements.txt before -e .
    differs from the reverse, and later installs can override earlier ones).
    """
    return hashlib.sha256(repr((url, commit, tuple(setup_commands))).encode()).hexdigest()


class RepoManager:
    def __init__(self, workspace_root: Path | None = None, use_uv: bool = False):
        self.workspace_root = workspace_root or Path("/tmp/awb-workspaces")
        self.use_uv = use_uv
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    async def _run(
        self, *args: str, cwd: Path | None = None, timeout: float = 300.0
    ) -> tuple[int, str, str]:
        """Run a git/cli command with a hard wall-clock timeout.

        Without this, a flaky network or wedged git operation can hang the
        whole runner indefinitely. Caller passes timeout per operation
        (typical: 300s for clones, 120s for checkouts, 60s for diffs).
        """
        result = await run_exec(*args, cwd=cwd, timeout=timeout)
        stderr = result.stderr.decode(errors="replace")
        if result.exit_code == 124:
            stderr = f"command timed out after {timeout}s: {' '.join(args)}"
        return result.exit_code, result.stdout.decode(errors="replace"), stderr

    async def _run_shell(
        self, cmd: str, cwd: Path | None = None, timeout: float = 300.0
    ) -> tuple[int, str, str]:
        result = await run_shell(cmd, cwd=cwd or Path.cwd(), timeout=timeout)
        stderr = result.stderr.decode(errors="replace")
        if result.exit_code == 124:
            stderr = f"shell command timed out after {timeout}s: {cmd}"
        return result.exit_code, result.stdout.decode(errors="replace"), stderr

    async def prepare(self, task: TaskDefinition, run_id: str | None = None) -> Path:
        workspace = self.workspace_root / (f"{task.id}_{run_id}" if run_id else task.id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        # Use bare-clone cache for faster repeated clones
        url_hash = hashlib.sha256(task.repo.url.encode()).hexdigest()[:16]
        mirror_dir = _CACHE_DIR / url_hash

        if not mirror_dir.exists():
            # First time — clone --mirror into cache
            last_err = ""
            for attempt in range(_CLONE_MAX_RETRIES):
                rc, _, err = await self._run(
                    "git", "clone", "--mirror", task.repo.url, str(mirror_dir)
                )
                if rc == 0:
                    break
                last_err = err
                if mirror_dir.exists():
                    shutil.rmtree(mirror_dir)
                if attempt < _CLONE_MAX_RETRIES - 1:
                    delay = _CLONE_BACKOFF_BASE * (attempt + 1)
                    log.warning(
                        "git clone --mirror failed for %s (attempt %d/%d), retrying in %ds",
                        task.id,
                        attempt + 1,
                        _CLONE_MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"git clone --mirror failed after {_CLONE_MAX_RETRIES} attempts: {last_err}"
                )

        # Workspace template cache: hash (url, commit, setup_commands) → skip pip install on hits
        template_key = _setup_cache_key(task.repo.url, task.repo.commit, task.repo.setup_commands)
        template_path = _TEMPLATE_DIR / template_key

        if (template_path / ".ready").exists():
            # Fast path: copy pre-built template instead of running setup_commands (~2s vs ~45s)
            shutil.rmtree(workspace)
            shutil.copytree(template_path, workspace, symlinks=True)
            # Template was built at the right commit — just ensure git state is clean
            rc, _, err = await self._run("git", "checkout", task.repo.commit, cwd=workspace)
            if rc != 0:
                raise RuntimeError(f"git checkout failed: {err}")
        else:
            # Slow path: clone, checkout, run setup, then cache the result
            rc, _, err = await self._run("git", "clone", "--local", str(mirror_dir), str(workspace))
            if rc != 0:
                raise RuntimeError(f"git clone --local failed: {err}")

            rc, _, err = await self._run("git", "checkout", task.repo.commit, cwd=workspace)
            if rc != 0:
                raise RuntimeError(f"git checkout failed: {err}")

            for cmd in task.repo.setup_commands:
                if self.use_uv:
                    cmd = cmd.replace("pip install", "uv pip install")
                result = await run_shell(cmd, cwd=workspace, timeout=600)
                if result.exit_code == 124:
                    raise RuntimeError(f"setup command timed out after 600s: {cmd}") from None
                if result.exit_code != 0:
                    raise RuntimeError(
                        f"setup command failed ({cmd}): {result.stderr.decode(errors='replace')}"
                    )

            # Cache the prepared workspace so future runs skip setup
            if template_path.exists():
                shutil.rmtree(template_path)
            shutil.copytree(workspace, template_path, symlinks=True)
            (template_path / ".ready").touch()

        # Write task-specific instructions after the cached template is copied.
        # Claude reads .claude/CLAUDE.md; Codex reads a root AGENTS override.
        if task.workspace_claude_md:
            claude_dir = workspace / ".claude"
            claude_dir.mkdir(exist_ok=True)
            (claude_dir / "CLAUDE.md").write_text(task.workspace_claude_md)

            agents_override = workspace / "AGENTS.override.md"
            existing_agents = agents_override
            if not existing_agents.exists():
                existing_agents = workspace / "AGENTS.md"
            existing_text = existing_agents.read_text() if existing_agents.exists() else ""
            if existing_text.strip():
                codex_instructions = (
                    existing_text.rstrip()
                    + "\n\n# AWB task-specific instructions\n\n"
                    + task.workspace_claude_md.lstrip()
                )
            else:
                codex_instructions = task.workspace_claude_md
            agents_override.write_text(codex_instructions)

        return workspace

    async def cleanup(self, workspace: Path) -> None:
        if workspace.exists():
            shutil.rmtree(workspace)

    def clear_templates(self) -> None:
        if _TEMPLATE_DIR.exists():
            shutil.rmtree(_TEMPLATE_DIR)
        _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    def get_diff(self, workspace: Path) -> str:
        import subprocess

        result = subprocess.run(
            ["git", "diff"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout

    def get_modified_files(self, workspace: Path) -> list[str]:
        import subprocess

        tracked = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        paths = tracked.stdout.splitlines() + untracked.stdout.splitlines()
        return sorted({path for path in paths if path})

    def capture_change_snapshot(self, workspace: Path) -> dict[str, bytes | None]:
        """Capture setup-time changes so result metrics can exclude them."""
        snapshot: dict[str, bytes | None] = {}
        for relative in self.get_modified_files(workspace):
            path = workspace / relative
            try:
                snapshot[relative] = path.read_bytes() if path.is_file() else None
            except OSError:
                snapshot[relative] = None
        return snapshot

    def get_modified_files_since(
        self, workspace: Path, baseline: dict[str, bytes | None]
    ) -> list[str]:
        current = self.capture_change_snapshot(workspace)
        return sorted(
            path for path in set(baseline) | set(current) if baseline.get(path) != current.get(path)
        )

    def get_lines_changed_since(self, workspace: Path, baseline: dict[str, bytes | None]) -> int:
        """Count added and removed lines relative to the pre-agent snapshot."""
        import subprocess

        current = self.capture_change_snapshot(workspace)
        total = 0
        for relative in self.get_modified_files_since(workspace, baseline):
            before = baseline.get(relative)
            after = current.get(relative)
            if before is not None:
                total += _line_delta(before, after or b"")
                continue
            if after is None:
                continue

            tracked = subprocess.run(
                ["git", "diff", "--numstat", "HEAD", "--", relative],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )
            fields = tracked.stdout.splitlines()[0].split("\t", 2) if tracked.stdout else []
            if len(fields) >= 2:
                with contextlib.suppress(ValueError):
                    total += int(fields[0]) + int(fields[1])
                    continue
            total += len(after.splitlines())
        return total

    def get_lines_changed(self, workspace: Path) -> int:
        import subprocess

        tracked = subprocess.run(
            ["git", "diff", "--numstat", "HEAD", "--"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        total = 0
        for line in tracked.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            with contextlib.suppress(ValueError):
                total += int(parts[0]) + int(parts[1])

        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=workspace,
            capture_output=True,
            timeout=60,
        )
        for raw_path in untracked.stdout.split(b"\0"):
            if not raw_path:
                continue
            path = workspace / raw_path.decode(errors="surrogateescape")
            if not path.is_file():
                continue
            with contextlib.suppress(OSError):
                data = path.read_bytes()
                total += len(data.splitlines()) if data else 0
        return total


def _line_delta(before: bytes, after: bytes) -> int:
    """Return git-style added-plus-removed line count for two snapshots."""
    before_lines = before.decode(errors="replace").splitlines()
    after_lines = after.decode(errors="replace").splitlines()
    total = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, before_lines, after_lines, autojunk=False
    ).get_opcodes():
        if tag != "equal":
            total += (i2 - i1) + (j2 - j1)
    return total
