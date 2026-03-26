"""Tests for tool adapters."""

import pytest

from awb.adapters.base import ToolAdapter, ToolResult
from awb.adapters.registry import get_adapter, list_adapters


class TestToolResult:
    def test_default_values(self):
        r = ToolResult(success=True)
        assert r.success is True
        assert r.raw_output == ""
        assert r.stream_events == []
        assert r.exit_code == 0

    def test_custom_values(self):
        r = ToolResult(success=False, exit_code=1, raw_output="error")
        assert r.success is False
        assert r.exit_code == 1


class TestRegistry:
    def test_list_adapters_returns_all(self):
        adapters = list_adapters()
        assert len(adapters) >= 2
        names = [a[0] for a in adapters]
        assert "claude-code-vanilla" in names
        assert "claude-code-custom" in names

    def test_get_known_adapter(self):
        adapter = get_adapter("claude-code-vanilla")
        assert isinstance(adapter, ToolAdapter)
        assert adapter.name == "claude-code-vanilla"

    def test_get_unknown_adapter_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent-tool")


class TestClaudeCodeVanilla:
    def test_adapter_properties(self):
        adapter = get_adapter("claude-code-vanilla")
        assert adapter.name == "claude-code-vanilla"
        assert "Vanilla" in adapter.display_name

    def test_config_hash_is_stable(self):
        adapter = get_adapter("claude-code-vanilla")
        h1 = adapter.get_config_hash()
        h2 = adapter.get_config_hash()
        assert h1 == h2


class TestClaudeCodeCustom:
    def test_adapter_properties(self):
        adapter = get_adapter("claude-code-custom")
        assert adapter.name == "claude-code-custom"
        assert "Custom" in adapter.display_name


def test_gemini_adapter_registered():
    from awb.adapters.registry import _FALLBACK

    assert "gemini-cli" in _FALLBACK


def test_codex_adapter_registered():
    from awb.adapters.registry import _FALLBACK

    assert "codex-cli" in _FALLBACK


def test_windsurf_adapter_registered():
    from awb.adapters.registry import _FALLBACK

    assert "windsurf" in _FALLBACK


def test_copilot_adapter_registered():
    from awb.adapters.registry import _FALLBACK

    assert "copilot" in _FALLBACK


def test_gemini_config_hash_deterministic():
    from awb.adapters.gemini_cli import GeminiCliAdapter

    adapter = GeminiCliAdapter()
    assert adapter.get_config_hash() == adapter.get_config_hash()


def test_codex_config_hash_deterministic():
    from awb.adapters.codex_cli import CodexCliAdapter

    adapter = CodexCliAdapter()
    assert adapter.get_config_hash() == adapter.get_config_hash()
