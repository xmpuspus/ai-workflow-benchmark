"""Claude Code adapters - vanilla (clean config) and custom (user's full config)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class ClaudeCodeVanillaAdapter(ToolAdapter):
    name = "claude-code-vanilla"
    display_name = "Claude Code (Vanilla)"

    @staticmethod
    def _clean_env(env: dict[str, str], keep: set[str] | None = None) -> dict[str, str]:
        """Remove inherited CLAUDE* vars that block nested sessions.

        Args:
            env: Environment dict to clean.
            keep: Set of CLAUDE* keys to preserve (e.g., ones we just set).
        """
        keep = keep or set()
        for key in list(env):
            if key.startswith("CLAUDE") and key not in keep:
                env.pop(key)
        return env

    def _get_env(self) -> dict[str, str]:
        """Build environment dict. Override in subclasses to change config."""
        env = dict(os.environ)
        env["CLAUDE_SKIP_HOOKS"] = "1"
        return self._clean_env(env, keep={"CLAUDE_SKIP_HOOKS"})

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        """Build command. Vanilla overrides system prompt to neutralize CLAUDE.md."""
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--max-turns",
            str(max_turns),
            "--verbose",
            "--dangerously-skip-permissions",
            "--system-prompt",
            "You are a helpful coding assistant. Complete the task described in the prompt.",
        ]

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        full_env = self._get_env()
        cmd = self._get_cmd(prompt, max_turns)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=full_env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )

            if proc.returncode != 0 and not stdout_bytes.strip():
                stderr_text = stderr_bytes.decode(errors="replace")[:500]
                from rich.console import Console

                Console(stderr=True).print(
                    f"[red]claude failed (exit {proc.returncode}):[/red] {stderr_text}"
                )

            # Check for "Not logged in" in stream output
            raw_check = stdout_bytes.decode(errors="replace")
            if "Not logged in" in raw_check:
                from rich.console import Console

                Console(stderr=True).print(
                    "[red]Claude Code is not logged in.[/red] "
                    "Run [bold]claude[/bold] interactively first to authenticate."
                )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(
                success=False,
                raw_output="",
                exit_code=124,
                tool_version=self.get_version(),
            )

        raw = stdout_bytes.decode(errors="replace")
        stream_events: list[dict] = []

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(json.JSONDecodeError):
                stream_events.append(json.loads(line))

        exit_code = proc.returncode or 0
        success = exit_code == 0

        # Extract model from stream events if present
        model = ""
        for event in stream_events:
            if not isinstance(event, dict):
                continue
            if "model" in event:
                model = event["model"]
                break
            # Check modelUsage in result events
            model_usage = event.get("modelUsage", {})
            if isinstance(model_usage, dict) and model_usage:
                model = next(iter(model_usage))
                break

        return ToolResult(
            success=success,
            raw_output=raw,
            stream_events=stream_events,
            exit_code=exit_code,
            tool_version=self.get_version(),
            model=model,
        )

    def check_available(self) -> bool:
        result = subprocess.run(["which", "claude"], capture_output=True, timeout=10)
        return result.returncode == 0

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                ["claude", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() or result.stderr.strip()
        except Exception:
            return "unknown"

    def get_config_hash(self) -> str:
        # Vanilla always uses an empty config dir - hash is constant
        return hashlib.sha256(b"vanilla-empty-config").hexdigest()[:16]

    def supports_auth_check(self) -> bool:
        return True

    def check_auth(self) -> tuple[bool, str]:
        """Check if claude is logged in."""
        try:
            cmd = self._get_cmd("echo test", 1)
            env = self._get_env()
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
            if "Not logged in" in result.stdout:
                return False, (
                    "Claude Code is not logged in. "
                    "Run 'claude' interactively first to authenticate, then re-run awb."
                )
            return True, ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, ""  # Timeout = probably working


class ClaudeCodeCustomAdapter(ClaudeCodeVanillaAdapter):
    """Runs Claude Code with the user's full ~/.claude configuration."""

    name = "claude-code-custom"
    display_name = "Claude Code (Custom)"

    def _get_env(self) -> dict[str, str]:
        """Use default config with benchmark mode to skip non-essential hooks."""
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"
        return self._clean_env(env)

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        """Custom uses full config — no --bare flag."""
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--max-turns",
            str(max_turns),
            "--verbose",
            "--dangerously-skip-permissions",
        ]

    def get_config_hash(self) -> str:
        """Hash key config files for reproducibility."""
        config_dir = Path.home() / ".claude"
        hasher = hashlib.sha256()

        # Hash settings.json
        settings = config_dir / "settings.json"
        if settings.exists():
            hasher.update(settings.read_bytes())

        # Count hooks, agents, skills
        counts = {}
        for subdir in ["hooks", "agents", "skills"]:
            d = config_dir / subdir
            if d.exists():
                counts[subdir] = sum(1 for _ in d.rglob("*") if _.is_file())
            else:
                counts[subdir] = 0

        hasher.update(json.dumps(counts, sort_keys=True).encode())
        return hasher.hexdigest()[:16]

    def get_version(self) -> str:
        """Return claude version plus config summary."""
        base = super().get_version()
        config_dir = Path.home() / ".claude"

        parts = [base]
        for subdir in ["hooks", "agents", "skills"]:
            d = config_dir / subdir
            if d.exists():
                count = sum(1 for _ in d.rglob("*.py") if _.is_file())
                parts.append(f"{count} {subdir}")

        return " + ".join(parts)
