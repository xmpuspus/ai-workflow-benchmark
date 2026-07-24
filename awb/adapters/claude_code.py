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
        on_event: object | None = None,
    ) -> ToolResult:
        full_env = self._get_env()
        cmd = self._get_cmd(prompt, max_turns)
        terminate = asyncio.Event()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=full_env,
                # stream-json lines carry whole file contents; asyncio's 64KB
                # readline default killed the reader mid-run (LimitOverrunError
                # during a real MF-001 probe).
                limit=10 * 1024 * 1024,
            )

            stream_events: list[dict] = []
            raw_lines: list[str] = []

            async def _read_stream():
                assert proc.stdout is not None
                while True:
                    try:
                        line_bytes = await proc.stdout.readline()
                    except ValueError:
                        # A single line beyond even the raised limit: drain the
                        # oversized chunk and keep reading rather than dying and
                        # silently starving the whole run of events.
                        with contextlib.suppress(Exception):
                            await proc.stdout.read(10 * 1024 * 1024)
                        continue
                    if not line_bytes:
                        break
                    line = line_bytes.decode(errors="replace").strip()
                    if not line:
                        continue
                    raw_lines.append(line)
                    with contextlib.suppress(json.JSONDecodeError):
                        event = json.loads(line)
                        stream_events.append(event)
                        if on_event is not None:
                            result = on_event(event)
                            if result is False:
                                terminate.set()

            async def _read_stderr():
                assert proc.stderr is not None
                stderr_chunks = []
                while True:
                    chunk = await proc.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)
                return b"".join(stderr_chunks)

            # Named tasks so they can be cancelled in `finally` if still
            # pending. Without this, the `terminate.wait()` task survives
            # past return on the happy path and asyncio logs
            # "Task was destroyed but it is pending!" at shutdown — same
            # for stderr_task on early-return (timeout) paths.
            stderr_task = asyncio.create_task(_read_stderr())
            read_task = asyncio.create_task(_read_stream())
            terminate_task = asyncio.create_task(terminate.wait())
            stderr_bytes = b""

            try:
                done, _ = await asyncio.wait(
                    {read_task, terminate_task},
                    timeout=timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if terminate.is_set():
                    # Token budget exceeded, kill gracefully
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except TimeoutError:
                        proc.kill()
                elif not done or read_task not in done:
                    # Timeout
                    proc.kill()
                    await proc.wait()
                    return ToolResult(
                        success=False,
                        raw_output="",
                        exit_code=124,
                        tool_version=self.get_version(),
                    )

                await proc.wait()
                stderr_bytes = await stderr_task

                if proc.returncode != 0 and not raw_lines:
                    stderr_text = stderr_bytes.decode(errors="replace")[:500]
                    from rich.console import Console

                    Console(stderr=True).print(
                        f"[red]claude failed (exit {proc.returncode}):[/red] {stderr_text}"
                    )

                # Check for "Not logged in" in stream output
                raw = "\n".join(raw_lines)
                if "Not logged in" in raw:
                    from rich.console import Console

                    Console(stderr=True).print(
                        "[red]Claude Code is not logged in.[/red] "
                        "Run [bold]claude[/bold] interactively first to authenticate."
                    )

            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    success=False,
                    raw_output="",
                    exit_code=124,
                    tool_version=self.get_version(),
                )
            finally:
                # Drain any still-pending tasks so asyncio does not log
                # "Task was destroyed but it is pending!" at shutdown.
                for task in (terminate_task, stderr_task, read_task):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task

        except FileNotFoundError:
            return ToolResult(
                success=False,
                raw_output="claude command not found",
                exit_code=127,
                tool_version="unknown",
            )

        raw = "\n".join(raw_lines)
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
                said = result.stdout.strip()[:200]
                return False, (
                    "Claude Code reported it is not logged in. If you are logged in, two "
                    "known causes: a CLAUDE_CONFIG_DIR override in the environment (unset "
                    "it), or a sandboxed/detached shell that cannot reach the macOS "
                    f"Keychain (run from a normal terminal). claude said: {said}"
                )
            return True, ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, ""  # Timeout = probably working


class ClaudeCodeCustomAdapter(ClaudeCodeVanillaAdapter):
    """Runs Claude Code with the user's full ~/.claude configuration."""

    name = "claude-code-custom"
    display_name = "Claude Code (Custom)"
    supports_config_dir = True

    def __init__(self, config_dir: Path | str | None = None) -> None:
        # None preserves the default behavior (user's real ~/.claude). Set
        # for `awb ab` to point the CLI at an alternate config directory.
        self.config_dir = Path(config_dir) if config_dir is not None else None

    def _get_env(self) -> dict[str, str]:
        """Use default config with benchmark mode to skip non-essential hooks."""
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"
        keep: set[str] = set()
        default_config = Path.home() / ".claude"
        if self.config_dir is not None and Path(self.config_dir).resolve() != default_config:
            # Only override when the dir actually differs from the default:
            # CLAUDE_CONFIG_DIR switches Claude Code to file-based credential
            # lookup, which misses macOS Keychain auth and reports logged-out
            # even though a default-config session works fine.
            env["CLAUDE_CONFIG_DIR"] = str(self.config_dir)
            keep.add("CLAUDE_CONFIG_DIR")
        return self._clean_env(env, keep=keep)

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
        config_dir = self.config_dir or (Path.home() / ".claude")
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
        # Mirror get_config_hash: an A/B run must record the overridden
        # config dir in its provenance, not the user's live ~/.claude.
        config_dir = self.config_dir or (Path.home() / ".claude")

        parts = [base]
        for subdir in ["hooks", "agents", "skills"]:
            d = config_dir / subdir
            if d.exists():
                count = sum(1 for _ in d.rglob("*.py") if _.is_file())
                parts.append(f"{count} {subdir}")

        return " + ".join(parts)
