"""Gemini CLI adapter for AI Workflow Benchmark."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.subprocesses import run_exec


class GeminiCliAdapter(ToolAdapter):
    """Adapter for Google's Gemini CLI."""

    name = "gemini-cli"
    display_name = "Gemini CLI"

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        return ["gemini", "-p", prompt, "--output-format", "json"]

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
        on_event=None,
    ) -> ToolResult:
        cmd = self._get_cmd(prompt, max_turns)
        env = self._get_env()
        result = await run_exec(*cmd, cwd=workspace, timeout=timeout_seconds, env=env)
        if result.exit_code == 124:
            return ToolResult(success=False, raw_output="", exit_code=124)

        stdout = result.stdout.decode("utf-8", errors="replace")
        stream_events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                stream_events.append(event)
                if on_event is not None and on_event(event) is False:
                    break
            except json.JSONDecodeError:
                continue

        return ToolResult(
            success=result.exit_code == 0 and bool(stdout.strip()),
            raw_output=stdout + result.stderr.decode("utf-8", errors="replace"),
            stream_events=stream_events,
            exit_code=result.exit_code,
            tool_version=self.get_version(),
            model="",
        )

    def check_available(self) -> bool:
        return shutil.which("gemini") is not None

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                ["gemini", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip().split("\n")[0] if result.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    def get_config_hash(self) -> str:
        h = hashlib.sha256()
        config_dir = Path.home() / ".gemini"
        if config_dir.exists():
            for f in sorted(config_dir.glob("*.json")):
                h.update(f.read_bytes())
        else:
            h.update(b"no-config")
        return h.hexdigest()[:16]
