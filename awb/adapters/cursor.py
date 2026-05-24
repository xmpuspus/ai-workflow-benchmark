"""Cursor IDE CLI adapter (placeholder)."""

from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CursorAdapter(ToolAdapter):
    name = "cursor"
    display_name = "Cursor"
    is_stub = True

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        raise NotImplementedError(
            "Cursor adapter is a stub. Install Cursor Agent CLI and implement "
            "execute() to enable. See awb/adapters/aider.py for the pattern."
        )

    def check_available(self) -> bool:
        return False

    def get_config_hash(self) -> str:
        return "cursor-stub"
