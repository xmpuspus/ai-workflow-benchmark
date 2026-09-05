"""Aider CLI adapter."""

from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.subprocesses import run_exec


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
        cmd = [
            "aider",
            "--message",
            prompt,
            "--yes",
            "--no-stream",
            "--no-auto-commits",
            "--no-show-model-warnings",
        ]
        result = await run_exec(*cmd, cwd=workspace, timeout=timeout_seconds)
        if result.exit_code == 124:
            return ToolResult(
                success=False,
                raw_output="",
                exit_code=124,
                tool_version=self.get_version(),
            )
        return ToolResult(
            success=result.exit_code == 0,
            raw_output=result.stdout.decode(errors="replace"),
            exit_code=result.exit_code,
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
