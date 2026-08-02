import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

_SCHEMA_PATH = Path(__file__).parent / "schema.json"


def _load_schema() -> dict:
    with _SCHEMA_PATH.open() as f:
        return json.load(f)


@dataclass
class ToolSpec:
    name: str
    version: str = ""


@dataclass
class ModelSpec:
    name: str = ""
    provider: str = ""


@dataclass
class ConfigSpec:
    max_turns: int = 20
    timeout_seconds: int = 1800
    config_hash: str = ""


@dataclass
class EnvironmentSpec:
    hooks_count: int = 0
    agents_count: int = 0
    skills_count: int = 0
    claude_md_hash: str = ""
    agents_md_hash: str = ""
    rules_count: int = 0
    plugins_count: int = 0


@dataclass
class WorkflowDescriptor:
    spec: str
    name: str
    tool: ToolSpec
    model: ModelSpec
    mode: str
    config: ConfigSpec
    environment: EnvironmentSpec
    metadata: dict = field(default_factory=dict)

    def descriptor_hash(self) -> str:
        canonical = {
            "spec": self.spec,
            "name": self.name,
            "tool": {"name": self.tool.name, "version": self.tool.version},
            "model": {"name": self.model.name, "provider": self.model.provider},
            "mode": self.mode,
            "config": {
                "max_turns": self.config.max_turns,
                "timeout_seconds": self.config.timeout_seconds,
                "config_hash": self.config.config_hash,
            },
            "environment": {
                "hooks_count": self.environment.hooks_count,
                "agents_count": self.environment.agents_count,
                "skills_count": self.environment.skills_count,
                "claude_md_hash": self.environment.claude_md_hash,
                "agents_md_hash": self.environment.agents_md_hash,
                "rules_count": self.environment.rules_count,
                "plugins_count": self.environment.plugins_count,
            },
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        return digest[:16]


def validate_descriptor(path: Path) -> list[str]:
    schema = _load_schema()
    try:
        with path.open() as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return [f"Failed to parse YAML: {e}"]

    validator = jsonschema.Draft7Validator(schema)
    return [e.message for e in sorted(validator.iter_errors(data), key=str)]


def load_descriptor(path: Path) -> WorkflowDescriptor:
    with path.open() as f:
        data = yaml.safe_load(f)

    tool_name = data.get("tool", "")
    tool = ToolSpec(name=tool_name)

    model_raw = data.get("model", "")
    model = ModelSpec(name=model_raw) if isinstance(model_raw, str) else ModelSpec(**model_raw)

    config_raw = data.get("config") or {}
    config = ConfigSpec(
        max_turns=config_raw.get("max_turns", 20),
        timeout_seconds=config_raw.get("timeout_seconds", 1800),
        config_hash=config_raw.get("config_hash", ""),
    )

    env_raw = data.get("environment") or {}
    environment = EnvironmentSpec(
        hooks_count=env_raw.get("hooks_count", 0),
        agents_count=env_raw.get("agents_count", 0),
        skills_count=env_raw.get("skills_count", 0),
        claude_md_hash=env_raw.get("claude_md_hash", ""),
        agents_md_hash=env_raw.get("agents_md_hash", ""),
        rules_count=env_raw.get("rules_count", 0),
        plugins_count=env_raw.get("plugins_count", 0),
    )

    return WorkflowDescriptor(
        spec=data.get("spec", ""),
        name=data.get("name", ""),
        tool=tool,
        model=model,
        mode=data.get("mode", "vanilla"),
        config=config,
        environment=environment,
        metadata=data.get("metadata") or {},
    )
