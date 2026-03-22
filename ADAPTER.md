# AWB Pi Adapter — Setup & Lessons Learned

## Overview

Custom adapter to benchmark [Pi](https://github.com/mariozechner/pi-coding-agent) (with full config: extensions, skills, memory, etc.) using [AWB](https://pypi.org/project/awb/) (AI Workflow Benchmark).

## Quick Setup

After `pip install awb` (or `uv pip install awb`), three files need patching in the installed package:

### 1. Create the adapter

Drop `pi.py` into the adapters directory:

```
.venv/lib/python3.13/site-packages/awb/adapters/pi.py
```

<details>
<summary>Full adapter source</summary>

```python
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
```

</details>

### 2. Register in the adapter registry

Edit `.venv/lib/python3.13/site-packages/awb/adapters/registry.py` — add to `_FALLBACK`:

```python
"pi": "awb.adapters.pi:PiAdapter",
```

### 3. Register the entry point

Edit `.venv/lib/python3.13/site-packages/awb-<version>.dist-info/entry_points.txt` — add under `[awb.adapters]`:

```
pi = awb.adapters.pi:PiAdapter
```

### 4. Verify

```bash
awb tools   # should show "Pi (Full Config) | Available"
```

## Re-patching after `pip install --upgrade awb`

The adapter file (`pi.py`) survives upgrades, but `registry.py` and `entry_points.txt` get overwritten. Re-apply steps 2 and 3.

## Key Design Decisions & Bugs Fixed

### 1. `stdin=subprocess.DEVNULL` — THE critical fix

**Problem:** Pi would hang indefinitely with 0% CPU and no network connections. It wrote ~6.5KB (session header) then went silent. Every benchmark task timed out.

**Root cause:** Without explicit `stdin`, `subprocess.Popen` inherits the parent's stdin. When AWB runs as a background process, its stdin is a unix socket from the process manager — not `/dev/null` or a TTY. Pi's Node.js runtime detected this non-standard stdin and blocked waiting on it.

**Fix:** `stdin=subprocess.DEVNULL` ensures Pi gets `/dev/null` as stdin, matching its `-p` (print/non-interactive) mode expectation.

### 2. Synchronous `subprocess.Popen` instead of `asyncio.create_subprocess_exec`

**Problem:** AWB's runner wraps `adapter.execute()` with `asyncio.wait_for(coro, timeout)`. When using async subprocess, the outer timeout cancellation killed the coroutine before it could capture Pi's output — resulting in 0 bytes raw_output on every run.

**Fix:** Use blocking `subprocess.Popen` + `proc.communicate(timeout=...)`. Even though `execute()` is `async def`, the blocking call ensures output is always captured before returning. AWB's async timeout can't interrupt a blocking syscall.

### 3. `start_new_session=True` for clean process group kills

Pi spawns child processes (bash commands, test runners, etc.). Using `os.killpg(proc.pid, SIGKILL)` on the process group ensures the entire tree is cleaned up on timeout — no zombie Pi processes left behind.

### 4. Environment cleaning

Strips `CLAUDE*` env vars and `PI_SESSION` to prevent the nested Pi from inheriting config from the parent session (which may be running inside Claude Code or another Pi instance).

## Running the Benchmark

```bash
# Single task test
awb run pi -t BF-001 --runs 1

# Full benchmark (60 tasks × 3 runs)
awb run pi --runs 3

# Filter by difficulty
awb run pi -d easy --runs 1

# Override timeout (seconds)
awb run pi --runs 1 --timeout 1500

# Analyze results
awb gap results/runs/<run_dir>/
```

## Performance Notes

- Pi with Opus 4.6 averages ~30-60s per easy task
- FastAPI repo tasks take longer due to large codebase (~48M workspace)
- The full 60×3 run takes roughly 3-5 hours with Opus
- Sonnet would be significantly faster if speed is prioritized over quality
