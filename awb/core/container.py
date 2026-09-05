"""Opt-in launcher for running the complete AWB pipeline in a local container."""

from __future__ import annotations

import subprocess
from pathlib import Path


def build_container_command(
    *, image: str, project_root: Path, results_dir: Path, cli_args: list[str]
) -> list[str]:
    """Build a narrow Docker command without host-home or ambient-secret mounts."""
    source = project_root.resolve()
    results = results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    return [
        "docker",
        "run",
        "--rm",
        "--init",
        "--network=none",
        "--mount",
        f"type=bind,src={source},dst=/opt/awb,readonly",
        "--mount",
        f"type=bind,src={results},dst=/results",
        "--workdir=/opt/awb",
        "--env=PYTHONPATH=/opt/awb",
        "--env=AWB_RESULTS_DIR=/results",
        image,
        "python3",
        "-c",
        "from awb.cli import cli; cli()",
        *cli_args,
        "--inside-container",
    ]


def launch_container(**kwargs) -> int:
    """Run Docker without forwarding the host environment or home directory."""
    command = build_container_command(**kwargs)
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError as exc:
        raise RuntimeError("Docker is required for --container-image") from exc
