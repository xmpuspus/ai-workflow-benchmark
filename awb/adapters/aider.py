"""Aider CLI adapter (placeholder)."""

from __future__ import annotations

from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class AiderAdapter(ToolAdapter):
    name = "aider"
    display_name = "Aider"

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        raise NotImplementedError("Aider adapter not yet implemented - contributions welcome")

    def check_available(self) -> bool:
        raise NotImplementedError("Aider adapter not yet implemented")

    def get_config_hash(self) -> str:
        return "n/a"
