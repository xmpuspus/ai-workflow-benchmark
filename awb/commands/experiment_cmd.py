"""Plan controlled comparisons and check portable evidence without model calls."""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import click

from awb.commands._shared import emit_json
from awb.experiments.evidence import build_bundle, verify_bundle
from awb.experiments.protocol import assess, create_plan, validate_plan


def _error(exc: Exception) -> None:
    emit_json({"status": "error", "error": str(exc)})
    raise click.exceptions.Exit(2) from exc


@click.group()
def experiment():
    """Plan a comparison, assess saved attempts, or verify an evidence bundle."""


@experiment.command("snapshot")
@click.argument("config_dir", type=click.Path(path_type=Path))
def snapshot_cmd(config_dir: Path):
    """Show permitted file names and hashes for a plan. Never prints file contents."""
    from awb.experiments.execution import config_snapshot

    try:
        snapshot = config_snapshot(config_dir)
        emit_json({key: value for key, value in snapshot.items() if key != "entries"})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)


@experiment.command("run")
@click.argument("plan_file", type=click.Path(path_type=Path))
@click.option("--config-a", required=True, type=click.Path(path_type=Path))
@click.option("--config-b", required=True, type=click.Path(path_type=Path))
@click.option("--tasks-dir", type=click.Path(path_type=Path))
@click.option("--split", type=click.Choice(["development", "holdout"]), default="development")
@click.option("--runs-dir", type=click.Path(path_type=Path), default="results/experiments")
def run_plan_cmd(
    plan_file: Path,
    config_a: Path,
    config_b: Path,
    tasks_dir: Path | None,
    split: str,
    runs_dir: Path,
):
    """Execute the frozen schedule. This explicitly calls the configured tool."""
    from awb.experiments.execution import execute_plan

    try:
        plan = json.loads(plan_file.read_text())
        validate_plan(plan)
        with contextlib.redirect_stdout(sys.stderr):
            result = execute_plan(plan, config_a, config_b, tasks_dir, split, runs_dir)
        emit_json(result)
        if result["status"] != "completed":
            raise click.exceptions.Exit(1)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        _error(exc)


@experiment.command("plan")
@click.argument("spec_file", type=click.Path(path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
def plan_cmd(spec_file: Path, out: Path):
    """Freeze a JSON specification and counterbalanced attempt schedule. No spend."""
    try:
        plan = create_plan(json.loads(spec_file.read_text()))
        with out.open("x") as handle:
            json.dump(plan, handle, indent=2)
            handle.write("\n")
        emit_json({"status": "planned", "path": str(out), "plan": plan})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)


@experiment.command("assess")
@click.argument("plan_file", type=click.Path(path_type=Path))
@click.argument("arm_a", type=click.Path(path_type=Path))
@click.argument("arm_b", type=click.Path(path_type=Path))
@click.option("--split", type=click.Choice(["development", "holdout"]), default="development")
def assess_cmd(plan_file: Path, arm_a: Path, arm_b: Path, split: str):
    """Assess two JSON arrays of attempts against a frozen plan."""
    try:
        result = assess(
            json.loads(plan_file.read_text()),
            json.loads(arm_a.read_text()),
            json.loads(arm_b.read_text()),
            split,
        )
        emit_json(result)
        if result["decision"] in {"inconclusive", "baseline_better"}:
            raise click.exceptions.Exit(1)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)


@experiment.command("bundle")
@click.argument("run_dir", type=click.Path(path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
def bundle_cmd(run_dir: Path, out: Path):
    """Copy task result JSON only. Review private metadata before sharing."""
    try:
        emit_json({"status": "created", "manifest": build_bundle(run_dir, out)})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)


@experiment.command("verify-bundle")
@click.argument("directory", type=click.Path(path_type=Path))
def verify_bundle_cmd(directory: Path):
    """Check every listed artifact and reject missing or unlisted files."""
    try:
        errors = verify_bundle(directory)
        emit_json({"status": "invalid" if errors else "verified", "errors": errors})
        if errors:
            raise click.exceptions.Exit(1)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)


@experiment.command("verify-plan")
@click.argument("path", type=click.Path(path_type=Path))
def verify_plan_cmd(path: Path):
    """Check that the plan still matches its declared specification."""
    try:
        validate_plan(json.loads(path.read_text()))
        emit_json({"status": "verified"})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        _error(exc)
