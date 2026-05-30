"""Aider CLI adapter."""

from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class AiderAdapter(ToolAdapter):
    """Aider CLI adapter.

    Real implementation over Aider's documented CLI:
    `aider --message <prompt> --yes --no-stream`. `check_available()` gates on
    the binary, so a missing Aider reports unavailable rather than crashing.
    Note: `--no-stream` means Aider emits no incremental tool events, so its
    `.trace.jsonl` has no gradeable spans and trace-grade columns show n/a for
    Aider runs (see grade_trace_or_none).
    """

    name = "aider"
    display_name = "Aider"
    is_stub = False

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
        on_event=None,
    ) -> ToolResult:
        import asyncio

        cmd = [
            "aider",
            "--message",
            prompt,
            "--yes",
            "--no-stream",
            "--no-auto-commits",
            "--no-show-model-warnings",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(
                success=False,
                raw_output="",
                exit_code=124,
                tool_version=self.get_version(),
            )
        return ToolResult(
            success=proc.returncode == 0,
            raw_output=stdout.decode(errors="replace"),
            exit_code=proc.returncode or 0,
            tool_version=self.get_version(),
        )

    def check_available(self) -> bool:
        import shutil

        return shutil.which("aider") is not None

    def get_version(self) -> str:
        import subprocess

        try:
            r = subprocess.run(["aider", "--version"], capture_output=True, text=True, timeout=10)
            return f"aider {r.stdout.strip()}"
        except Exception:
            return "aider unknown"

    def get_config_hash(self) -> str:
        import hashlib
        import os

        cfg = Path.home() / ".aider.conf.yml"
        h = hashlib.sha256()
        if cfg.exists():
            h.update(cfg.read_bytes())
        env_bits = ":".join(
            f"{k}={os.environ.get(k, '')}"
            for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
            if os.environ.get(k)
        )
        h.update(env_bits.encode())
        return h.hexdigest()[:16]
