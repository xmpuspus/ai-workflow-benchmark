from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import shutil
from pathlib import Path

from awb.core.config import TaskDefinition

log = logging.getLogger(__name__)

_CLONE_MAX_RETRIES = 3
_CLONE_BACKOFF_BASE = 5  # seconds
_CACHE_DIR = Path.home() / ".cache" / "awb" / "clones"


class RepoManager:
    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or Path("/tmp/awb-workspaces")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

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

        # Clone from local cache (fast, no network)
        rc, _, err = await self._run(
            "git", "clone", "--local", str(mirror_dir), str(workspace)
        )
        if rc != 0:
            raise RuntimeError(f"git clone --local failed: {err}")

        rc, _, err = await self._run("git", "checkout", task.repo.commit, cwd=workspace)
        if rc != 0:
            raise RuntimeError(f"git checkout failed: {err}")

        for cmd in task.repo.setup_commands:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=workspace,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"setup command failed ({cmd}): {stderr.decode(errors='replace')}"
                    )
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError(f"setup command timed out after 600s: {cmd}") from None

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
