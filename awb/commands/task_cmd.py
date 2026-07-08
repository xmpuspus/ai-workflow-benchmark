"""task command group - mine private benchmark tasks from merged PRs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click
import yaml

from awb.commands._shared import BAD, INFO, OK, console, emit_json

_CATEGORIES = (
    "bug-fix",
    "feature-addition",
    "refactoring",
    "code-review",
    "debugging",
    "multi-file",
    "legacy-code",
    "workflow",
)

_CATEGORY_PREFIX = {
    "bug-fix": "BF",
    "feature-addition": "FA",
    "refactoring": "RF",
    "code-review": "CR",
    "debugging": "DB",
    "multi-file": "MF",
    "legacy-code": "LC",
    "workflow": "WF",
}

_ID_RE = re.compile(r"^[A-Z]{2}-(\d{3})$")


def _next_task_id(category: str, search_dirs: list[Path]) -> str:
    """Next free ID for the category's prefix, scanning all search_dirs for collisions."""
    prefix = _CATEGORY_PREFIX[category]
    used: set[int] = set()
    for d in search_dirs:
        if not d.exists():
            continue
        for path in d.rglob(f"{prefix}-*.yaml"):
            match = _ID_RE.match(path.stem)
            if match:
                used.add(int(match.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{prefix}-{n:03d}"


@click.group(name="task")
def task():
    """Manage benchmark task definitions."""


@task.command("from-pr")
@click.argument("pr_url")
@click.option(
    "--out",
    type=click.Path(),
    default="./tasks",
    help="Directory to write the task YAML into",
)
@click.option("--id", "task_id", help="Task ID (default: next free ID for the category)")
@click.option(
    "--category", type=click.Choice(_CATEGORIES), default="feature-addition", help="Task category"
)
@click.option(
    "--difficulty",
    type=click.Choice(["easy", "medium", "hard"]),
    default="medium",
    help="Task difficulty",
)
@click.option("--estimated-minutes", type=int, default=30, help="Estimated completion time")
@click.option(
    "--test-command",
    default="python -m pytest",
    help="Base test command used to build verification checks",
)
@click.option(
    "--setup-command",
    "setup_commands",
    multiple=True,
    help="Extra setup command to run before the test overlay (repeatable)",
)
@click.option(
    "--contamination-risk",
    type=click.Choice(["low", "medium", "high", "unknown"]),
    default="low",
    help="Estimated likelihood this task leaked into a training corpus",
)
@click.option("--dry-run", is_flag=True, help="Print the generated YAML without writing anything")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the task dict and written path on stdout.",
)
def from_pr(
    pr_url: str,
    out: str,
    task_id: str | None,
    category: str,
    difficulty: str,
    estimated_minutes: int,
    test_command: str,
    setup_commands: tuple[str, ...],
    contamination_risk: str,
    dry_run: bool,
    fmt: str,
):
    """Mine a benchmark task from a merged GitHub pull request."""
    from awb.core.config import TASKS_DIR
    from awb.core.pr_miner import PrMinerError, mine_task_from_pr
    from awb.core.task_loader import validate_task_yaml

    if task_id and not _ID_RE.match(task_id):
        raise click.UsageError(f"--id must match [A-Z]{{2}}-NNN, got: {task_id}")

    try:
        mined = mine_task_from_pr(
            pr_url,
            category=category,
            difficulty=difficulty,
            estimated_minutes=estimated_minutes,
            test_command=test_command,
            extra_setup_commands=list(setup_commands),
            contamination_risk=contamination_risk,
        )
    except PrMinerError as e:
        # style= instead of markup tags: the error can embed PR-derived text.
        console.print(str(e), style=BAD, markup=False)
        sys.exit(1)

    out_dir = Path(out)
    chosen_id = task_id or _next_task_id(category, [out_dir, TASKS_DIR])
    mined.task["id"] = chosen_id

    yaml_text = yaml.dump(mined.task, default_flow_style=False, sort_keys=False)

    if dry_run:
        if fmt == "json":
            emit_json({"task": mined.task, "written_path": None})
        else:
            console.print(f"[{INFO}]Dry run - nothing written[/{INFO}]\n")
            # markup=False: the YAML embeds PR-author-controlled text; a title
            # like "Fix bug[/x]" would raise MarkupError mid-print.
            console.print(yaml_text, markup=False)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{chosen_id}.yaml"
    out_path.write_text(yaml_text)

    errors = validate_task_yaml(out_path)
    if errors:
        console.print(f"[{BAD}]Generated task failed validation:[/{BAD}]")
        for e in errors:
            # jsonschema messages quote PR-derived field values; no markup.
            console.print(f"  - {e}", markup=False)
        sys.exit(1)

    if fmt == "json":
        emit_json({"task": mined.task, "written_path": str(out_path)})
    else:
        console.print(f"[{OK}]Task written:[/{OK}] {out_path}")
        console.print(f"  pre-merge commit: {mined.premerge_sha[:12]}")
        console.print(f"  test files overlaid: {len(mined.test_files)}")
        console.print(f"  source files: {len(mined.source_files)}")
