"""Codex CLI adapter for AI Workflow Benchmark."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CodexCliAdapter(ToolAdapter):
    """Adapter for OpenAI's Codex CLI."""

    name = "codex-cli"
    display_name = "Codex CLI"

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        return ["codex", "-p", prompt, "--output-format", "json"]

    def _get_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"
        for key in list(env):
            if key.startswith("CLAUDE"):
                del env[key]
        return env

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        cmd = self._get_cmd(prompt, max_turns)
        env = self._get_env()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(success=False, raw_output="", exit_code=-1)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stream_events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                stream_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return ToolResult(
            success=proc.returncode == 0 and bool(stdout.strip()),
            raw_output=stdout + stderr_bytes.decode("utf-8", errors="replace"),
            stream_events=stream_events,
            exit_code=proc.returncode or 0,
            tool_version=self.get_version(),
            model="",
        )

    def check_available(self) -> bool:
        return shutil.which("codex") is not None

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip().split("\n")[0] if result.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    def get_config_hash(self) -> str:
        h = hashlib.sha256()
        config_dir = Path.home() / ".codex"
        if config_dir.exists():
            for f in sorted(config_dir.glob("*.json")):
                h.update(f.read_bytes())
        else:
            h.update(b"no-config")
        return h.hexdigest()[:16]
