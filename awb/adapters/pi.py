"""Pi coding agent adapter - runs with user's full Pi configuration."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class PiAdapter(ToolAdapter):
    """Runs Pi with the user's full ~/.pi/agent configuration."""

    name = "pi"
    display_name = "Pi (Full Config)"

    @staticmethod
    def _clean_env(env: dict[str, str]) -> dict[str, str]:
        """Remove vars that block nested Pi sessions."""
        for key in list(env):
            if key.startswith("CLAUDE") or key == "PI_SESSION":
                env.pop(key)
        return env

    def _get_env(self) -> dict[str, str]:
        env = self._clean_env(dict(os.environ))
        env["AWB_BENCHMARK"] = "1"
        return env

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        full_env = self._get_env()

        cmd = [
            "pi",
            "-p",
            prompt,
            "--mode",
            "json",
            "--no-session",
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,   # CRITICAL — prevents hang
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            env=full_env,
            start_new_session=True,     # own process group for clean kill
        )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            stdout_bytes, stderr_bytes = proc.communicate(timeout=10)
        except Exception:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                proc.communicate(timeout=10)
            return ToolResult(
                success=False, raw_output="", exit_code=1,
                tool_version=self.get_version(),
            )

        raw = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
        stream_events: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(json.JSONDecodeError):
                stream_events.append(json.loads(line))

        exit_code = proc.returncode or 0
        timed_out = exit_code == -9
        success = exit_code == 0

        model = ""
        for event in stream_events:
            if not isinstance(event, dict):
                continue
            msg = event.get("message", {})
            if isinstance(msg, dict) and msg.get("model"):
                model = msg["model"]
                break

        return ToolResult(
            success=success,
            raw_output=raw,
            stream_events=stream_events,
            exit_code=124 if timed_out else exit_code,
            tool_version=self.get_version(),
            model=model,
        )

    def check_available(self) -> bool:
        result = subprocess.run(["which", "pi"], capture_output=True, timeout=10)
        return result.returncode == 0

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                ["pi", "--version"], capture_output=True, text=True, timeout=10
            )
            version = result.stdout.strip() or result.stderr.strip()
            return f"pi {version}"
        except Exception:
            return "pi unknown"

    def get_config_hash(self) -> str:
        config_dir = Path.home() / ".pi" / "agent"
        hasher = hashlib.sha256()
        for path in [config_dir / "settings.json", config_dir / "AGENTS.md"]:
            if path.exists():
                hasher.update(path.read_bytes())
        counts = {}
        for subdir in ["extensions", "skills", "prompts"]:
            d = config_dir / subdir
            counts[subdir] = sum(1 for _ in d.rglob("*") if _.is_file()) if d.exists() else 0
        hasher.update(json.dumps(counts, sort_keys=True).encode())
        return hasher.hexdigest()[:16]
