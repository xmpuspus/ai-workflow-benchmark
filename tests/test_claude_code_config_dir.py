"""Tests for ClaudeCodeCustomAdapter's config_dir override (used by `awb ab`)."""

from __future__ import annotations

from awb.adapters.base import ToolAdapter
from awb.adapters.claude_code import ClaudeCodeCustomAdapter, ClaudeCodeVanillaAdapter


def test_base_adapter_supports_config_dir_defaults_false():
    assert ToolAdapter.supports_config_dir is False


def test_vanilla_adapter_does_not_support_config_dir():
    assert ClaudeCodeVanillaAdapter.supports_config_dir is False


def test_custom_adapter_supports_config_dir():
    assert ClaudeCodeCustomAdapter.supports_config_dir is True


def test_config_dir_accepts_string_path(tmp_path):
    adapter = ClaudeCodeCustomAdapter(config_dir=str(tmp_path))
    assert adapter.config_dir == tmp_path


def test_get_env_without_config_dir_omits_claude_config_dir():
    adapter = ClaudeCodeCustomAdapter()
    env = adapter._get_env()
    assert "CLAUDE_CONFIG_DIR" not in env
    assert env["AWB_BENCHMARK"] == "1"


def test_get_env_with_config_dir_sets_claude_config_dir(tmp_path):
    adapter = ClaudeCodeCustomAdapter(config_dir=tmp_path)
    env = adapter._get_env()
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert env["AWB_BENCHMARK"] == "1"


def test_get_env_default_strips_inherited_claude_vars(monkeypatch):
    # Byte-for-byte parity with pre-config_dir behavior: any inherited
    # CLAUDE* var not explicitly set by us gets stripped.
    monkeypatch.setenv("CLAUDE_SOME_OTHER_VAR", "leftover")
    adapter = ClaudeCodeCustomAdapter()
    env = adapter._get_env()
    assert "CLAUDE_SOME_OTHER_VAR" not in env
    assert "CLAUDE_CONFIG_DIR" not in env


def test_get_config_hash_default_matches_registry_instance():
    from awb.adapters.registry import get_adapter

    via_registry = get_adapter("claude-code-custom")
    direct = ClaudeCodeCustomAdapter()
    assert via_registry.get_config_hash() == direct.get_config_hash()


def test_get_config_hash_uses_override_dir_not_home(tmp_path):
    config_dir = tmp_path / "claude-config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_bytes(b'{"unique": "marker-value"}')

    adapter = ClaudeCodeCustomAdapter(config_dir=config_dir)
    default_adapter = ClaudeCodeCustomAdapter()
    assert adapter.get_config_hash() != default_adapter.get_config_hash()


def test_get_config_hash_deterministic_for_same_content(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "settings.json").write_bytes(b'{"x": 1}')
    (dir_b / "settings.json").write_bytes(b'{"x": 1}')

    adapter_a = ClaudeCodeCustomAdapter(config_dir=dir_a)
    adapter_b = ClaudeCodeCustomAdapter(config_dir=dir_b)
    assert adapter_a.get_config_hash() == adapter_b.get_config_hash()


def test_get_config_hash_changes_with_different_settings(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "settings.json").write_bytes(b'{"x": 1}')
    (dir_b / "settings.json").write_bytes(b'{"x": 2}')

    adapter_a = ClaudeCodeCustomAdapter(config_dir=dir_a)
    adapter_b = ClaudeCodeCustomAdapter(config_dir=dir_b)
    assert adapter_a.get_config_hash() != adapter_b.get_config_hash()


def test_get_config_hash_counts_hooks_agents_skills(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    (dir_a / "hooks").mkdir(parents=True)
    (dir_b / "hooks").mkdir(parents=True)
    (dir_a / "hooks" / "one.py").write_text("x")
    (dir_b / "hooks" / "one.py").write_text("x")
    (dir_b / "hooks" / "two.py").write_text("y")

    adapter_a = ClaudeCodeCustomAdapter(config_dir=dir_a)
    adapter_b = ClaudeCodeCustomAdapter(config_dir=dir_b)
    assert adapter_a.get_config_hash() != adapter_b.get_config_hash()


def test_get_version_counts_from_override_dir(tmp_path):
    from awb.adapters.claude_code import ClaudeCodeCustomAdapter

    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "one.py").write_text("x = 1\n")
    adapter = ClaudeCodeCustomAdapter(config_dir=tmp_path)
    version = adapter.get_version()
    # Provenance must describe the overridden config dir, not ~/.claude.
    assert "1 hooks" in version
