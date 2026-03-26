"""Resolve workflow descriptors to adapters."""

from __future__ import annotations

from awb.adapters.base import ToolAdapter
from awb.adapters.registry import get_adapter
from awb.workflow.descriptor import WorkflowDescriptor


def resolve_adapter(descriptor: WorkflowDescriptor) -> ToolAdapter:
    """Get the adapter instance for a workflow descriptor's tool."""
    return get_adapter(descriptor.tool.name)


def get_workflow_metadata(descriptor: WorkflowDescriptor) -> dict:
    """Flatten descriptor into a dict suitable for result JSON."""
    return {
        "spec": descriptor.spec,
        "name": descriptor.name,
        "tool": descriptor.tool.name,
        "tool_version": descriptor.tool.version,
        "model": descriptor.model.name,
        "model_provider": descriptor.model.provider,
        "mode": descriptor.mode,
        "descriptor_hash": descriptor.descriptor_hash(),
        "config": {
            "max_turns": descriptor.config.max_turns,
            "timeout_seconds": descriptor.config.timeout_seconds,
            "config_hash": descriptor.config.config_hash,
        },
        "environment": {
            "hooks_count": descriptor.environment.hooks_count,
            "agents_count": descriptor.environment.agents_count,
            "skills_count": descriptor.environment.skills_count,
            "claude_md_hash": descriptor.environment.claude_md_hash,
        },
        **descriptor.metadata,
    }
