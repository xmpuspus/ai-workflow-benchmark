"""Regression test for the stub-adapter fail-fast guard.

Stub adapters (cursor, aider, windsurf, copilot) used to raise
NotImplementedError mid-run after workspace setup wasted ~30s. The fix sets
is_stub = True on the class and adds a check at the top of run_single.
"""

from __future__ import annotations

import pytest

from awb.adapters.aider import AiderAdapter
from awb.adapters.copilot_cli import CopilotCliAdapter
from awb.adapters.cursor import CursorAdapter
from awb.adapters.windsurf import WindsurfAdapter


@pytest.mark.parametrize(
    "adapter_cls", [CursorAdapter, AiderAdapter, WindsurfAdapter, CopilotCliAdapter]
)
def test_stub_adapters_advertise_is_stub(adapter_cls) -> None:
    """Every stub adapter must set is_stub = True at class level."""
    assert getattr(adapter_cls, "is_stub", False), (
        f"{adapter_cls.__name__} is a stub but is_stub is not True. "
        "Set `is_stub = True` so the runner can fail fast at startup."
    )


def test_real_adapter_does_not_set_is_stub() -> None:
    """The Claude Code adapter ships real execute() and must not be marked stub."""
    from awb.adapters.claude_code import ClaudeCodeCustomAdapter

    assert getattr(ClaudeCodeCustomAdapter, "is_stub", False) is False
