"""GitHub Copilot CLI adapter — stub pending agentic CLI mode."""

from __future__ import annotations

import subprocess
from pathlib import Path

from awb.adapters.base import ToolAdapter, ToolResult


class CopilotCliAdapter(ToolAdapter):
    name = "copilot"
    display_name = "GitHub Copilot CLI"

    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        raise NotImplementedError(
            "Copilot CLI adapter requires 'gh copilot' with agentic mode. "
            "Currently Copilot CLI is suggestion-based, not agentic."
        )

    def check_available(self) -> bool:
        try:
            result = subprocess.run(
                ["gh", "extension", "list"], capture_output=True, text=True, timeout=10
            )
            return "copilot" in result.stdout.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_config_hash(self) -> str:
        return "copilot-stub"
