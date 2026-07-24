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


def test_on_event_signature_is_callable_typed():
    """ToolAdapter.execute(on_event=...) must be a Callable, not bare object."""
    import inspect

    from awb.adapters.base import StreamEventCallback, ToolAdapter

    sig = inspect.signature(ToolAdapter.execute)
    on_event_param = sig.parameters["on_event"]
    annotation_str = str(on_event_param.annotation)
    assert "Callable" in annotation_str or "StreamEventCallback" in annotation_str, (
        f"on_event still typed as {annotation_str!r} — expected Callable or StreamEventCallback"
    )
    # Sanity: the alias itself exists and points at a Callable
    assert "Callable" in str(StreamEventCallback)


class TestConfigDirDefaultSkipsOverride:
    """CLAUDE_CONFIG_DIR pointing at the real default breaks macOS Keychain auth:
    Claude Code switches to file-based credential lookup and reports logged-out.
    Found live: `awb checkup` defaults --config-dir to ~/.claude and could never
    pass the auth preflight on a Keychain-authed machine."""

    def test_default_config_dir_does_not_set_env_override(self):
        import pathlib

        from awb.adapters.claude_code import ClaudeCodeCustomAdapter

        adapter = ClaudeCodeCustomAdapter(config_dir=pathlib.Path.home() / ".claude")
        assert "CLAUDE_CONFIG_DIR" not in adapter._get_env()

    def test_non_default_config_dir_still_sets_env_override(self, tmp_path):
        from awb.adapters.claude_code import ClaudeCodeCustomAdapter

        adapter = ClaudeCodeCustomAdapter(config_dir=tmp_path)
        assert adapter._get_env()["CLAUDE_CONFIG_DIR"] == str(tmp_path)


class TestStreamReaderLongLines:
    """A stream-json line over asyncio's 64KB default readline limit killed the
    reader task with LimitOverrunError mid-run (seen live during MF-001)."""

    def test_execute_survives_a_100kb_stream_line(self, tmp_path):
        import asyncio
        import json as _json
        import sys

        from awb.adapters.claude_code import ClaudeCodeVanillaAdapter

        big = _json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 100_000}]}}
        )
        script = tmp_path / "fake_claude.py"
        script.write_text(
            "import sys\n"
            f"sys.stdout.write({big!r} + chr(10))\n"
            'sys.stdout.write(\'{"type": "result", "result": "done", '
            '"total_cost_usd": 0.01}\' + chr(10))\n'
        )
        adapter = ClaudeCodeVanillaAdapter()
        adapter._get_cmd = lambda prompt, max_turns: [sys.executable, str(script)]
        result = asyncio.run(adapter.execute("do a thing", tmp_path, timeout_seconds=30))
        assert "x" * 1000 in str(result)


class TestCheckAuthDiagnostics:
    """The old message guessed "run claude interactively" for every failure; the
    two live failures were a CLAUDE_CONFIG_DIR override and a sandboxed shell."""

    def test_not_logged_in_message_names_known_causes_and_quotes_output(self, monkeypatch):
        import subprocess as sp

        from awb.adapters.claude_code import ClaudeCodeVanillaAdapter

        def fake_run(*args, **kwargs):
            return sp.CompletedProcess(args=args, returncode=1, stdout="Not logged in", stderr="")

        monkeypatch.setattr("awb.adapters.claude_code.subprocess.run", fake_run)
        ok, msg = ClaudeCodeVanillaAdapter().check_auth()
        assert not ok
        assert "CLAUDE_CONFIG_DIR" in msg
        assert "Keychain" in msg
        assert "Not logged in" in msg
