"""workflow command group — export, validate, diff, init."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.table import Table

from awb.commands._shared import console


@click.group()
def workflow():
    """Manage workflow descriptors."""
    pass


@workflow.command("export")
@click.argument("tool")
@click.option("--name", "-n", required=True, help="Workflow name")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--config-dir", type=click.Path(file_okay=False), help="Alternate tool config dir")
def workflow_export(tool: str, name: str, output: str | None, config_dir: str | None):
    """Generate a workflow descriptor YAML from current tool config."""
    from awb.workflow.exporter import export_workflow

    out = Path(output) if output else None
    path = export_workflow(
        tool,
        name,
        output_path=out,
        config_dir=Path(config_dir) if config_dir else None,
    )
    console.print(f"Workflow exported: [bold]{path}[/bold]")


@workflow.command("validate")
@click.argument("file", type=click.Path(exists=True))
def workflow_validate(file: str):
    """Validate a workflow descriptor YAML."""
    from awb.workflow.descriptor import validate_descriptor

    errors = validate_descriptor(Path(file))
    if errors:
        console.print(f"[red]FAIL[/red] {file}")
        for e in errors:
            console.print(f"  - {e}")
        sys.exit(1)
    else:
        console.print(f"[green]PASS[/green] {file}")


@workflow.command("diff")
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
def workflow_diff(file1: str, file2: str):
    """Compare two workflow descriptors."""
    from awb.workflow.descriptor import load_descriptor

    d1 = load_descriptor(Path(file1))
    d2 = load_descriptor(Path(file2))

    table = Table(title=f"Workflow Diff: {d1.name} vs {d2.name}")
    table.add_column("Field")
    table.add_column(d1.name)
    table.add_column(d2.name)
    table.add_column("Match")

    comparisons = [
        ("tool", d1.tool.name, d2.tool.name),
        ("mode", d1.mode, d2.mode),
        ("model", d1.model.name, d2.model.name),
        ("max_turns", str(d1.config.max_turns), str(d2.config.max_turns)),
        ("timeout", str(d1.config.timeout_seconds), str(d2.config.timeout_seconds)),
        ("config_hash", d1.config.config_hash, d2.config.config_hash),
        ("hooks", str(d1.environment.hooks_count), str(d2.environment.hooks_count)),
        ("agents", str(d1.environment.agents_count), str(d2.environment.agents_count)),
        ("skills", str(d1.environment.skills_count), str(d2.environment.skills_count)),
        ("rules", str(d1.environment.rules_count), str(d2.environment.rules_count)),
        ("plugins", str(d1.environment.plugins_count), str(d2.environment.plugins_count)),
        ("descriptor_hash", d1.descriptor_hash(), d2.descriptor_hash()),
    ]

    for field, v1, v2 in comparisons:
        match = "[green]=[/green]" if v1 == v2 else "[red]!=[/red]"
        table.add_row(field, v1, v2, match)

    console.print(table)


@workflow.command("init")
@click.option("--output", "-o", type=click.Path(), default="workflow.yaml", help="Output file")
def workflow_init(output: str):
    """Interactively create a workflow descriptor."""
    from awb.adapters.registry import list_adapters

    adapters = list_adapters()
    adapter_names = [a[0] for a in adapters]

    console.print("[bold]Create a new workflow descriptor[/bold]\n")
    name = click.prompt("Workflow name")
    tool = click.prompt("Tool", type=click.Choice(adapter_names))
    model = click.prompt("Model (optional)", default="")
    max_turns = click.prompt("Max turns", default=20, type=int)
    timeout_s = click.prompt("Timeout (seconds)", default=1800, type=int)

    import yaml

    from awb.workflow.exporter import export_claude_code_config, export_codex_config

    descriptor = {
        "spec": "awb/v1",
        "name": name,
        "tool": tool,
        "mode": "custom" if tool in {"claude-code-custom", "codex-cli"} else "vanilla",
        "config": {
            "max_turns": max_turns,
            "timeout_seconds": timeout_s,
        },
    }
    if model:
        descriptor["model"] = model
    if tool == "claude-code-custom":
        descriptor["environment"] = export_claude_code_config()
    elif tool == "codex-cli":
        environment, config_hash, configured_model = export_codex_config()
        descriptor["environment"] = environment
        descriptor["config"]["config_hash"] = config_hash
        if not model and configured_model:
            descriptor["model"] = configured_model

    out = Path(output)
    out.write_text(yaml.dump(descriptor, default_flow_style=False, sort_keys=False))
    console.print(f"\nWorkflow created: [bold]{out}[/bold]")
