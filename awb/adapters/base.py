"""Abstract base for tool adapters."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolResult:
    """Normalized output from a tool execution."""

    success: bool
    raw_output: str = ""
    stream_events: list[dict] = field(default_factory=list)
    exit_code: int = 0
    tool_version: str = ""
    model: str = ""


class ToolAdapter(abc.ABC):
    """Base class for AI coding tool adapters."""

    name: str  # e.g. "claude-code-vanilla"
    display_name: str  # e.g. "Claude Code (Vanilla)"

    @abc.abstractmethod
    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
    ) -> ToolResult:
        """Run the tool against a task in the given workspace."""
        ...

    @abc.abstractmethod
    def check_available(self) -> bool:
        """Return True if this tool is installed and usable."""
        ...

    @abc.abstractmethod
    def get_config_hash(self) -> str:
        """Return a hash of the tool's configuration for reproducibility."""
        ...

    def get_version(self) -> str:
        """Return tool version string."""
        return "unknown"
