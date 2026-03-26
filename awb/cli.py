"""CLI interface for the AI Workflow Benchmark."""
from __future__ import annotations

import click

from awb import __version__
from awb.commands.analyze import compare, gap, stability
from awb.commands.calibrate import calibrate_difficulty_cmd, calibrate_timeouts_cmd
from awb.commands.leaderboard_cmd import leaderboard
from awb.commands.migrate import migrate_results
from awb.commands.run import run
from awb.commands.submit import compare_submissions_cmd, export, submit
from awb.commands.validate import info, quickstart, tools, validate
from awb.commands.workflow_cmd import workflow


@click.group()
@click.version_option(version=__version__, prog_name="awb")
def cli():
    """AI Workflow Benchmark - measure tool+workflow performance."""
    pass


cli.add_command(run)
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
