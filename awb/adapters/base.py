"""Abstract base for tool adapters."""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# A stream-event callback. The adapter calls it for every streamed event;
# returning False signals "stop now" (used for token-budget enforcement).
# Required key:
#   - "type": str   one of "assistant", "tool_use", "result"
# Optional keys (when type == "assistant"):
#   - "message": {"usage": {"input_tokens": int, "output_tokens": int,
#                            "cache_read_input_tokens": int,
#                            "cache_creation_input_tokens": int},
#                  "content": [{"type": "tool_use", "name": str, ...}, ...]}
# Optional keys (when type == "tool_use"):
#   - "tool" or "name": str        tool name
# Optional keys (when type == "result"):
#   - "total_cost_usd" or "cost_usd": float
#   - "usage": same shape as assistant.message.usage
#   - "num_turns": int
StreamEventCallback = Callable[[dict], bool | None]


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

    # Stub adapters set this to True so the runner can fail fast at startup
    # instead of provisioning a workspace and then hitting NotImplementedError.
    is_stub: bool = False

    # Adapters that can relocate their CLI config directory (needed for
    # `awb ab` config A/B testing) set this to True and accept a `config_dir`
    # constructor kwarg.
    supports_config_dir: bool = False

    @abc.abstractmethod
    async def execute(
        self,
        prompt: str,
        workspace: Path,
        max_turns: int = 20,
        timeout_seconds: int = 1800,
        on_event: StreamEventCallback | None = None,
    ) -> ToolResult:
        """Run the tool against a task in the given workspace.

        Args:
            on_event: Optional callback invoked for each streamed event. Return
                False to request early termination (used for token-budget
                enforcement); return None or True to continue. See the
                StreamEventCallback type alias above for the event schema.
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
