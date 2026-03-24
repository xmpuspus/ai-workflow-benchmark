from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path

from awb.core.config import TaskDefinition

log = logging.getLogger(__name__)

_CLONE_MAX_RETRIES = 3
_CLONE_BACKOFF_BASE = 5  # seconds


class RepoManager:
    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or Path("/tmp/awb-workspaces")
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    async def _run(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(), stderr.decode()

    async def _run_shell(self, cmd: str, cwd: Path | None = None) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(), stderr.decode()

    async def prepare(self, task: TaskDefinition, run_id: str | None = None) -> Path:
        workspace = self.workspace_root / (f"{task.id}_{run_id}" if run_id else task.id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        # Git clone with retry — concurrent clones can hit GitHub rate limits
        last_err = ""
        for attempt in range(_CLONE_MAX_RETRIES):
            rc, _, err = await self._run("git", "clone", task.repo.url, str(workspace))
            if rc == 0:
                break
            last_err = err
            if attempt < _CLONE_MAX_RETRIES - 1:
                delay = _CLONE_BACKOFF_BASE * (attempt + 1)
                log.warning(
                    "git clone failed for %s (attempt %d/%d), retrying in %ds",
                    task.id, attempt + 1, _CLONE_MAX_RETRIES, delay,
                )
                # Clean up partial clone before retry
                if workspace.exists():
                    shutil.rmtree(workspace)
                workspace.mkdir(parents=True)
                await asyncio.sleep(delay)
        else:
            raise RuntimeError(f"git clone failed after {_CLONE_MAX_RETRIES} attempts: {last_err}")

        rc, _, err = await self._run("git", "checkout", task.repo.commit, cwd=workspace)
        if rc != 0:
            raise RuntimeError(f"git checkout failed: {err}")

        for cmd in task.repo.setup_commands:
            rc, _, err = await self._run_shell(cmd, cwd=workspace)
            if rc != 0:
                raise RuntimeError(f"setup command failed ({cmd}): {err}")

        # Write workspace CLAUDE.md if task defines one
        if task.workspace_claude_md:
            claude_dir = workspace / ".claude"
            claude_dir.mkdir(exist_ok=True)
            (claude_dir / "CLAUDE.md").write_text(task.workspace_claude_md)

        return workspace

    async def cleanup(self, workspace: Path) -> None:
        if workspace.exists():
            shutil.rmtree(workspace)

    def get_diff(self, workspace: Path) -> str:
        import subprocess

        result = subprocess.run(
            ["git", "diff"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def get_modified_files(self, workspace: Path) -> list[str]:
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        return [line for line in lines if line]

    def get_lines_changed(self, workspace: Path) -> int:
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        total = 0
        for line in result.stdout.splitlines():
            # lines like: " 3 files changed, 42 insertions(+), 7 deletions(-)"
            if "insertion" in line or "deletion" in line:
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if "insertion" in part or "deletion" in part:
                        with contextlib.suppress(ValueError, IndexError):
                            total += int(part.split()[0])
        return total
