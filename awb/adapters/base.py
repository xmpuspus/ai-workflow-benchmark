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
        on_event: object | None = None,
    ) -> ToolResult:
        """Run the tool against a task in the given workspace.

        Args:
            on_event: Optional callback(event_dict) called for each stream event
                as it arrives. Used for real-time token monitoring and budget
                enforcement. Return False from callback to request early termination.
        """
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

    def supports_auth_check(self) -> bool:
        """Return True if this adapter can verify authentication."""
        return False

    def check_auth(self) -> tuple[bool, str]:
        """Check if the tool is authenticated. Returns (ok, message)."""
        return True, ""

    def supports_streaming(self) -> bool:
        """Return True if this adapter supports streaming output."""
        return False

    def get_model_pricing(self) -> dict[str, float]:
        """Return pricing per 1M tokens: {input_per_m, output_per_m}."""
        return {"input_per_m": 15.0, "output_per_m": 75.0}
