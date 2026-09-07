"""CLI interface for the AI Workflow Benchmark."""

from __future__ import annotations

import logging

import click

from awb import __version__
from awb.commands.ab_cmd import ab
from awb.commands.analyze import compare, gap, stability
from awb.commands.calibrate import calibrate_difficulty_cmd, calibrate_timeouts_cmd
from awb.commands.checkup_cmd import checkup
from awb.commands.cost_cmd import cost
from awb.commands.drift_cmd import drift
from awb.commands.experiment_cmd import experiment
from awb.commands.leaderboard_cmd import leaderboard
from awb.commands.migrate import migrate_results
from awb.commands.report import report
from awb.commands.run import run
from awb.commands.submit import compare_submissions_cmd, export, submit
from awb.commands.task_cmd import task
from awb.commands.trace_cmd import trace
from awb.commands.validate import info, quickstart, tools, validate
from awb.commands.warmup import warmup
from awb.commands.workflow_cmd import workflow


class WorkflowCommands(click.Group):
    """Organize discovery around the next action while keeping command names stable."""

    def format_commands(self, ctx, formatter):
        sections = {
            "Start here (free)": ["quickstart", "report", "validate", "info", "tools"],
            "Audit and compare": ["checkup", "run", "experiment", "ab", "compare", "drift"],
            "Inspect evidence": ["gap", "cost", "stability", "trace", "leaderboard"],
            "Prepare and share": ["task", "workflow", "warmup", "export", "submit"],
        }
        known = {name for names in sections.values() for name in names}
        sections["Other commands"] = [name for name in self.list_commands(ctx) if name not in known]
        for heading, names in sections.items():
            rows = []
            for name in names:
                command = self.get_command(ctx, name)
                if command is not None and not command.hidden:
                    rows.append((name, command.get_short_help_str()))
            if rows:
                with formatter.section(heading):
                    formatter.write_dl(rows)


@click.group(cls=WorkflowCommands)
@click.version_option(version=__version__, prog_name="awb")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool):
    """AI Workflow Benchmark - measure tool+workflow performance.

    Start here: quickstart for local setup, checkup --static-only for a free
    harness audit, then report last to read saved evidence.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


cli.add_command(run)
cli.add_command(experiment)
cli.add_command(report)
cli.add_command(checkup)
cli.add_command(compare)
cli.add_command(gap)
cli.add_command(stability)
cli.add_command(calibrate_difficulty_cmd)
cli.add_command(calibrate_timeouts_cmd)
cli.add_command(export)
cli.add_command(submit)
cli.add_command(compare_submissions_cmd)
cli.add_command(validate)
cli.add_command(info)
cli.add_command(quickstart)
cli.add_command(tools)
cli.add_command(leaderboard)
cli.add_command(workflow)
cli.add_command(migrate_results)
cli.add_command(warmup)
cli.add_command(trace)
cli.add_command(task)
cli.add_command(ab)
cli.add_command(drift)
cli.add_command(cost)
