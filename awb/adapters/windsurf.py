"""Windsurf adapter — stub pending CLI availability."""

from __future__ import annotations

import shutil
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class WindsurfAdapter(ToolAdapter):
    name = "windsurf"
    display_name = "Windsurf"
    is_stub = True

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        raise NotImplementedError(
            "Windsurf adapter requires Windsurf CLI (not yet publicly available). "
            "Check https://windsurf.com for CLI release updates."
        )

    def check_available(self) -> bool:
        return shutil.which("windsurf") is not None

    def get_config_hash(self) -> str:
        return "windsurf-stub"
