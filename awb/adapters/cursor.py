"""Cursor IDE CLI adapter (placeholder)."""
from __future__ import annotations

import shutil
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CursorAdapter(ToolAdapter):
    name = "cursor"
    display_name = "Cursor"

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        raise NotImplementedError(
            "Cursor adapter not yet implemented - contributions welcome"
        )

    def check_available(self) -> bool:
        return shutil.which("cursor") is not None

    def get_config_hash(self) -> str:
        return "n/a"
