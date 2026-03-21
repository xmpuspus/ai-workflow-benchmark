"""Tests for workflow descriptor module."""
from pathlib import Path

import pytest
import yaml

from awb.adapters.base import ToolAdapter
from awb.workflow.descriptor import (
    ConfigSpec,
    EnvironmentSpec,
    ModelSpec,
    ToolSpec,
    WorkflowDescriptor,
    load_descriptor,
    validate_descriptor,
)
from awb.workflow.exporter import export_workflow
from awb.workflow.loader import resolve_adapter


def _make_valid_yaml(tmp_path: Path, extra: dict | None = None) -> Path:
    data = {
        "spec": "awb/v1",
        "name": "test-workflow",
        "tool": "claude-code-vanilla",
        "mode": "vanilla",
    }
    if extra:
        data.update(extra)
    p = tmp_path / "workflow.yaml"
    p.write_text(yaml.dump(data))
    return p


def _make_descriptor(tool_name: str = "claude-code-vanilla") -> WorkflowDescriptor:
    return WorkflowDescriptor(
        spec="awb/v1",
        name="test",
        tool=ToolSpec(name=tool_name),
        model=ModelSpec(),
        mode="vanilla",
        config=ConfigSpec(),
        environment=EnvironmentSpec(),
    )


class TestValidateDescriptor:
    def test_valid(self, tmp_path):
        p = _make_valid_yaml(tmp_path)
        assert validate_descriptor(p) == []

    def test_missing_required(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump({"spec": "awb/v1", "name": "x"}))
        errors = validate_descriptor(p)
        assert any("tool" in e for e in errors)

    def test_wrong_spec(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump({"spec": "awb/v2", "name": "x", "tool": "aider"}))
        assert validate_descriptor(p)

    def test_invalid_tool(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump({"spec": "awb/v1", "name": "x", "tool": "unknown-tool"}))
        assert validate_descriptor(p)

    def test_bad_yaml(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("{ not: valid: yaml: :")
        assert validate_descriptor(p)


class TestLoadDescriptor:
    def test_minimal(self, tmp_path):
        p = _make_valid_yaml(tmp_path)
        d = load_descriptor(p)
        assert d.spec == "awb/v1"
        assert d.name == "test-workflow"
        assert d.tool.name == "claude-code-vanilla"

    def test_full(self, tmp_path):
        p = _make_valid_yaml(tmp_path, {
            "model": "claude-opus-4",
            "config": {"max_turns": 10, "timeout_seconds": 600, "config_hash": "abc123"},
            "environment": {"hooks_count": 5, "agents_count": 3},
            "metadata": {"author": "xavier"},
        })
        d = load_descriptor(p)
        assert d.model.name == "claude-opus-4"
        assert d.config.max_turns == 10
        assert d.environment.hooks_count == 5
        assert d.metadata["author"] == "xavier"

    def test_defaults(self, tmp_path):
        p = _make_valid_yaml(tmp_path)
        d = load_descriptor(p)
        assert d.config.max_turns == 20
        assert d.config.timeout_seconds == 1800
        assert d.environment.hooks_count == 0


class TestDescriptorHash:
    def test_stable(self):
        d = _make_descriptor()
        assert d.descriptor_hash() == d.descriptor_hash()
        assert len(d.descriptor_hash()) == 16

    def test_differs_by_name(self):
        d1 = _make_descriptor()
        d2 = _make_descriptor()
        d2.name = "different"
        assert d1.descriptor_hash() != d2.descriptor_hash()

    def test_differs_by_tool(self):
        d1 = _make_descriptor("claude-code-vanilla")
        d2 = _make_descriptor("aider")
        assert d1.descriptor_hash() != d2.descriptor_hash()


class TestExportWorkflow:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "wf.yaml"
        result = export_workflow("claude-code-vanilla", "wf", output_path=out)
        assert result == out
        assert out.exists()

    def test_valid_yaml(self, tmp_path):
        out = tmp_path / "wf.yaml"
        export_workflow("claude-code-vanilla", "test-wf", output_path=out)
        data = yaml.safe_load(out.read_text())
        assert data["spec"] == "awb/v1"
        assert data["name"] == "test-wf"
        assert data["tool"] == "claude-code-vanilla"

    def test_custom_includes_environment(self, tmp_path):
        out = tmp_path / "wf.yaml"
        export_workflow("claude-code-custom", "custom", output_path=out)
        data = yaml.safe_load(out.read_text())
        assert "environment" in data

    def test_vanilla_no_environment(self, tmp_path):
        out = tmp_path / "wf.yaml"
        export_workflow("claude-code-vanilla", "vanilla", output_path=out)
        data = yaml.safe_load(out.read_text())
        assert "environment" not in data

    def test_passes_validation(self, tmp_path):
        out = tmp_path / "wf.yaml"
        export_workflow("aider", "aider-wf", output_path=out)
        assert validate_descriptor(out) == []


class TestResolveAdapter:
    def test_vanilla(self):
        d = _make_descriptor("claude-code-vanilla")
        adapter = resolve_adapter(d)
        assert isinstance(adapter, ToolAdapter)
        assert adapter.name == "claude-code-vanilla"

    def test_custom(self):
        d = _make_descriptor("claude-code-custom")
        adapter = resolve_adapter(d)
        assert isinstance(adapter, ToolAdapter)

    def test_unknown_raises(self):
        d = _make_descriptor("unknown-tool")
        with pytest.raises(ValueError, match="Unknown adapter"):
            resolve_adapter(d)
