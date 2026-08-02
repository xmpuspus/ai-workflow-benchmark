import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import yaml


def export_claude_code_config() -> dict:
    claude_dir = Path.home() / ".claude"

    def count_files(subdir: str) -> int:
        d = claude_dir / subdir
        if not d.is_dir():
            return 0
        return sum(1 for p in d.iterdir() if p.is_file())

    claude_md = claude_dir / "CLAUDE.md"
    claude_md_hash = ""
    if claude_md.is_file():
        digest = hashlib.sha256(claude_md.read_bytes()).hexdigest()
        claude_md_hash = digest[:16]

    return {
        "hooks_count": count_files("hooks"),
        "agents_count": count_files("agents"),
        "skills_count": count_files("skills"),
        "claude_md_hash": claude_md_hash,
    }


def _entry_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if not path.name.startswith("."))


def _hook_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    if not isinstance(hooks, dict):
        return 0
    total = 0
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                total += len(group["hooks"])
    return total


def export_codex_config(config_dir: Path | None = None) -> tuple[dict, str, str]:
    """Return Codex harness inventory, config hash, and configured model."""
    from awb.adapters.codex_cli import CodexCliAdapter

    codex_dir = config_dir or (Path.home() / ".codex")
    default_codex_dir = Path.home() / ".codex"
    agents_dir = (
        Path.home() / ".agents" if codex_dir.resolve() == default_codex_dir.resolve() else None
    )

    config_data: dict = {}
    config_path = codex_dir / "config.toml"
    try:
        with config_path.open("rb") as handle:
            loaded = tomllib.load(handle)
        if isinstance(loaded, dict):
            config_data = loaded
    except (OSError, tomllib.TOMLDecodeError):
        pass

    active_agents = codex_dir / "AGENTS.override.md"
    if not active_agents.exists():
        active_agents = codex_dir / "AGENTS.md"
    agents_md_hash = ""
    if active_agents.is_file():
        agents_md_hash = hashlib.sha256(active_agents.read_bytes()).hexdigest()[:16]

    plugins = config_data.get("plugins", {})
    enabled_plugins = (
        {
            name
            for name, settings in plugins.items()
            if isinstance(settings, dict) and settings.get("enabled") is True
        }
        if isinstance(plugins, dict)
        else set()
    )
    if agents_dir is not None and (agents_dir / "plugins").is_dir():
        enabled_plugins.update(
            path.name
            for path in (agents_dir / "plugins").iterdir()
            if not path.name.startswith(".") and path.name != "marketplace.json"
        )

    skills_count = _entry_count(codex_dir / "skills")
    agents_count = _entry_count(codex_dir / "agents")
    if agents_dir is not None:
        skills_count += _entry_count(agents_dir / "skills")
        agents_count += _entry_count(agents_dir / "agents")

    environment = {
        "hooks_count": _hook_count(codex_dir / "hooks.json"),
        "agents_count": agents_count,
        "skills_count": skills_count,
        "claude_md_hash": "",
        "agents_md_hash": agents_md_hash,
        "rules_count": len(list((codex_dir / "rules").glob("*.rules"))),
        "plugins_count": len(enabled_plugins),
    }
    adapter = CodexCliAdapter(config_dir=codex_dir)
    return environment, adapter.get_config_hash(), adapter.model


def export_workflow(
    tool_name: str,
    workflow_name: str,
    output_path: Path | None = None,
    config_dir: Path | None = None,
) -> Path:
    if output_path is None:
        output_path = Path.cwd() / f"{workflow_name}.yaml"

    mode = "custom" if tool_name in {"claude-code-custom", "codex-cli"} else "vanilla"

    descriptor: dict = {
        "spec": "awb/v1",
        "name": workflow_name,
        "tool": tool_name,
        "mode": mode,
        "config": {
            "max_turns": 20,
            "timeout_seconds": 1800,
            "config_hash": "",
        },
        "metadata": {
            "created": datetime.now(UTC).isoformat(),
        },
    }

    if tool_name == "claude-code-custom":
        descriptor["environment"] = export_claude_code_config()
    elif tool_name == "codex-cli":
        environment, config_hash, model = export_codex_config(config_dir)
        descriptor["environment"] = environment
        descriptor["config"]["config_hash"] = config_hash
        if model:
            descriptor["model"] = model

    output_path.write_text(yaml.dump(descriptor, default_flow_style=False, sort_keys=False))
    return output_path
