"""warmup command — pre-build workspace templates for faster benchmark runs."""

from __future__ import annotations

import asyncio
import hashlib

import click
from rich.table import Table

from awb.commands._shared import INFO, console


def _template_key(url: str, commit: str, setup_commands: list[str]) -> str:
    key = f"{url}:{commit}:{':'.join(sorted(setup_commands))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@click.command()
@click.option("--dry-run", is_flag=True, help="Show unique combos without building")
@click.option("--clear", is_flag=True, help="Clear template cache")
@click.option("--use-uv", is_flag=True, help="Use uv instead of pip for faster installs")
@click.option(
    "--fast-check",
    is_flag=True,
    help="Warm only the 8 fast-check task repos (first-time setup ~1-2 min instead of ~5)",
)
def warmup(dry_run: bool, clear: bool, use_uv: bool, fast_check: bool) -> None:
    """Pre-build workspace templates for faster benchmark runs."""
    from awb.core.repo_manager import RepoManager
    from awb.core.task_loader import load_all_tasks

    if clear:
        mgr = RepoManager()
        mgr.clear_templates()
        console.print("[green]Template cache cleared[/green]")
        return

    tasks = load_all_tasks()

    if fast_check:
        from awb.core.fast_check import select_fast_check_tasks

        tasks = select_fast_check_tasks(tasks)
        console.print(f"[bold {INFO}]Fast-check mode:[/bold {INFO}] warming {len(tasks)} repos")

    # Discover unique (url, commit, setup_commands) combinations
    seen: dict[str, dict] = {}
    for task in tasks:
        key = _template_key(task.repo.url, task.repo.commit, task.repo.setup_commands)
        if key not in seen:
            seen[key] = {
                "url": task.repo.url,
                "commit": task.repo.commit,
                "setup_commands": task.repo.setup_commands,
                "task_ids": [],
            }
        seen[key]["task_ids"].append(task.id)

    table = Table(title=f"Workspace Templates ({len(seen)} unique)")
    table.add_column("Key")
    table.add_column("Repo")
    table.add_column("Tasks")
    table.add_column("Setup")
    for key, info in seen.items():
        repo_short = info["url"].split("/")[-1]
        setup_short = info["setup_commands"][0][:60] + "..." if info["setup_commands"] else "(none)"
        table.add_row(key[:8], repo_short, str(len(info["task_ids"])), setup_short)
    console.print(table)

    if dry_run:
        console.print(f"\n[dim]{len(seen)} templates to build, {len(tasks)} tasks total[/dim]")
        return

    console.print(f"\nBuilding {len(seen)} templates...")
    mgr = RepoManager(use_uv=use_uv)

    async def _build_all() -> None:
        for key, info in seen.items():
            representative_id = info["task_ids"][0]
            representative = next(t for t in tasks if t.id == representative_id)
            try:
                workspace = await mgr.prepare(representative, run_id="warmup")
                await mgr.cleanup(workspace)
                console.print(
                    f"  [green][DONE][/green] {key[:8]} "
                    f"({info['url'].split('/')[-1]}, {len(info['task_ids'])} tasks)"
                )
            except Exception as e:
                console.print(f"  [red][FAIL][/red] {key[:8]} ({info['url'].split('/')[-1]}): {e}")

    asyncio.run(_build_all())
    console.print(f"\n[green]Warmup complete — {len(seen)} templates cached[/green]")
