"""OpenAI Codex CLI adapter for AI Workflow Benchmark."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from awb.adapters.base import StreamEventCallback, ToolAdapter, ToolResult


class CodexCliAdapter(ToolAdapter):
    """Run Codex non-interactively with the user's configured harness."""

    name = "codex-cli"
    display_name = "Codex CLI (Custom)"
    supports_config_dir = True
    _streams_events_inline = True

    _CHATGPT_CREDIT_RATES = {
        "gpt-5.6-sol": (125.0, 12.5, 750.0),
        "gpt-5.6-terra": (62.5, 6.25, 375.0),
        "gpt-5.6-luna": (25.0, 2.5, 150.0),
        "gpt-5.5": (125.0, 12.5, 750.0),
        "gpt-5.4": (62.5, 6.25, 375.0),
        "gpt-5.4-mini": (18.75, 1.875, 113.0),
        "gpt-5.3-codex": (43.75, 4.375, 350.0),
        "gpt-5.2": (43.75, 4.375, 350.0),
    }

    def __init__(self, config_dir: Path | str | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else None
        self.model = str(self._read_config().get("model") or "")

    def _effective_config_dir(self) -> Path:
        return self.config_dir or (Path.home() / ".codex")

    def _read_config(self) -> dict:
        path = self._effective_config_dir() / "config.toml"
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def _get_cmd(self, prompt: str, max_turns: int) -> list[str]:
        """Build the documented Codex non-interactive JSONL command.

        Codex has no CLI max-turn flag. AWB still enforces the task's wall-clock
        and token budgets while the JSONL stream is running.
        """
        return [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--json",
            prompt,
        ]

    def _get_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["AWB_BENCHMARK"] = "1"

        # A benchmark invocation is a fresh CLI process, not a continuation of
        # the parent Claude/Codex thread that happened to launch AWB.
        for key in list(env):
            if key.startswith("CLAUDE") or key in {
                "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
                "CODEX_SANDBOX",
                "CODEX_SANDBOX_NETWORK_DISABLED",
                "CODEX_THREAD_ID",
            }:
                env.pop(key)

        default_config = Path.home() / ".codex"
        if self.config_dir is not None and self.config_dir.resolve() != default_config.resolve():
            env["CODEX_HOME"] = str(self.config_dir)
        else:
            env.pop("CODEX_HOME", None)
        return env

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
        on_event: StreamEventCallback | None = None,
    ) -> ToolResult:
        cmd = self._get_cmd(prompt, max_turns)
        env = self._get_env()
        proc: asyncio.subprocess.Process | None = None
        stream_events: list[dict] = []
        raw_lines: list[str] = []
        stderr_bytes = b""
        terminate = asyncio.Event()

        async def _stop_process() -> None:
            if proc is None or proc.returncode is not None:
                return
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError, OSError):
                    os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=env,
                limit=10 * 1024 * 1024,
                start_new_session=True,
            )

            async def _read_stdout() -> None:
                assert proc is not None and proc.stdout is not None
                while True:
                    try:
                        line_bytes = await proc.stdout.readline()
                    except ValueError:
                        # Keep the stream alive if one event exceeds the raised
                        # asyncio line limit. Codex can emit large tool output
                        # in a single JSON object.
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
                        if not isinstance(event, dict):
                            continue
                        stream_events.append(event)
                        if on_event is not None and on_event(event) is False:
                            terminate.set()

            async def _read_stderr() -> bytes:
                assert proc is not None and proc.stderr is not None
                chunks = []
                while True:
                    chunk = await proc.stderr.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                return b"".join(chunks)

            stdout_task = asyncio.create_task(_read_stdout())
            stderr_task = asyncio.create_task(_read_stderr())
            terminate_task = asyncio.create_task(terminate.wait())

            try:
                done, _ = await asyncio.wait(
                    {stdout_task, terminate_task},
                    timeout=timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if terminate.is_set():
                    await _stop_process()
                elif not done or stdout_task not in done:
                    await _stop_process()
                    return ToolResult(
                        success=False,
                        raw_output="\n".join(raw_lines),
                        stream_events=stream_events,
                        exit_code=124,
                        tool_version=self.get_version(),
                        model=self.model,
                    )

                await proc.wait()
                stderr_bytes = await stderr_task
            finally:
                for task in (terminate_task, stderr_task, stdout_task):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task

        except asyncio.CancelledError:
            if proc is not None:
                await _stop_process()
            raise
        except FileNotFoundError:
            return ToolResult(
                success=False,
                raw_output="codex command not found",
                exit_code=127,
                tool_version="unknown",
                model=self.model,
            )
        except Exception as exc:  # keep adapter failures as result evidence
            if proc is not None:
                await _stop_process()
            return ToolResult(
                success=False,
                raw_output=str(exc),
                stream_events=stream_events,
                exit_code=1,
                tool_version=self.get_version(),
                model=self.model,
            )

        stderr = stderr_bytes.decode(errors="replace").strip()
        raw = "\n".join(raw_lines)
        if stderr:
            raw = f"{raw}\n{stderr}" if raw else stderr
        exit_code = proc.returncode or 0
        return ToolResult(
            success=exit_code == 0 and bool(stream_events),
            raw_output=raw,
            stream_events=stream_events,
            exit_code=exit_code,
            tool_version=self.get_version(),
            model=self.model,
        )

    def check_available(self) -> bool:
        return shutil.which("codex") is not None

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, timeout=10
            )
            version = result.stdout.strip() or result.stderr.strip()
            return version.splitlines()[0] if result.returncode == 0 and version else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    def supports_auth_check(self) -> bool:
        return True

    def check_auth(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["codex", "login", "status"],
                capture_output=True,
                text=True,
                env=self._get_env(),
                timeout=15,
            )
        except FileNotFoundError:
            return False, "Codex CLI is not installed."
        except subprocess.TimeoutExpired:
            return False, "Codex authentication check timed out."

        if result.returncode == 0:
            return True, ""
        said = (result.stdout or result.stderr).strip()[:300]
        return False, f"Codex CLI is not authenticated for this CODEX_HOME. codex said: {said}"

    def supports_streaming(self) -> bool:
        return True

    def get_model_pricing(self) -> dict[str, Any]:
        """Return ChatGPT Codex credit rates for the configured model.

        One credit is valued at $0.04 for AWB's existing dollar-normalized
        score, matching OpenAI's published 2,500 credits = $100 equivalence.
        The native credit estimate is retained alongside that conversion.
        """
        normalized = self.model.lower().replace("_", "-")
        rates = self._CHATGPT_CREDIT_RATES.get(normalized)
        if rates is None:
            return super().get_model_pricing()
        multiplier = 2.5 if self._read_config().get("service_tier") == "fast" else 1.0
        input_rate, cached_rate, output_rate = rates
        return {
            "billing_unit": "credits",
            "input_per_m": input_rate * multiplier,
            "cached_input_per_m": cached_rate * multiplier,
            "output_per_m": output_rate * multiplier,
            "usd_per_credit": 0.04,
        }

    def get_config_hash(self) -> str:
        """Hash behavior-bearing Codex files without touching auth or session state."""
        config_dir = self._effective_config_dir()
        hasher = hashlib.sha256()
        candidates = [
            config_dir / "config.toml",
            config_dir / "AGENTS.override.md",
            config_dir / "AGENTS.md",
            config_dir / "hooks.json",
        ]
        for pattern in ("rules/*.rules", "agents/*.toml", "skills/**/SKILL.md"):
            candidates.extend(config_dir.glob(pattern))

        seen = False
        for path in sorted({p for p in candidates if p.is_file()}, key=lambda p: str(p)):
            seen = True
            with contextlib.suppress(OSError):
                hasher.update(str(path.relative_to(config_dir)).encode())
                hasher.update(path.read_bytes())
        if not seen:
            hasher.update(b"no-codex-config")
        return hasher.hexdigest()[:16]
