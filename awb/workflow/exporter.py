import hashlib
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


def export_workflow(
    tool_name: str,
    workflow_name: str,
    output_path: Path | None = None,
) -> Path:
    if output_path is None:
        output_path = Path.cwd() / f"{workflow_name}.yaml"

    mode = "custom" if tool_name == "claude-code-custom" else "vanilla"

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

    output_path.write_text(yaml.dump(descriptor, default_flow_style=False, sort_keys=False))
    return output_path
