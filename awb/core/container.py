"""Opt-in launcher for running the complete AWB pipeline in a local container."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path


def build_container_command(
    *,
    image: str,
    project_root: Path,
    results_dir: Path,
    cli_args: list[str],
    container_name: str | None = None,
    input_mounts: list[tuple[Path, str]] | None = None,
) -> list[str]:
    """Build a narrow Docker command without host-home or ambient-secret mounts."""
    source = project_root.resolve()
    results = results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    mounts = []
    for path, target in input_mounts or []:
        if path.is_symlink() or path.resolve() in {Path.home().resolve(), Path("/")}:
            raise ValueError("Refusing a broad or symlink container input")
        if target not in {"/inputs/tasks", "/inputs/workflow.yaml"}:
            raise ValueError("Unknown container input target")
        if not path.exists():
            raise ValueError("Container input does not exist")
        mounts.extend(["--mount", f"type=bind,src={path.resolve()},dst={target},readonly"])
    return [
        "docker",
        "run",
        "--rm",
        "--init",
        "--name",
        container_name or f"awb-{uuid.uuid4().hex[:12]}",
        "--network=none",
        "--cpus=2",
        "--memory=4g",
        "--pids-limit=256",
        "--read-only",
        "--tmpfs=/tmp:rw,exec,size=8g",
        "--mount",
        f"type=bind,src={source},dst=/opt/awb,readonly",
        "--mount",
        f"type=bind,src={results},dst=/results",
        "--workdir=/tmp/awb-home",
        "--env=PYTHONPATH=/opt/awb",
        "--env=AWB_RESULTS_DIR=/results",
        "--env=HOME=/tmp/awb-home",
        "--env=XDG_CACHE_HOME=/tmp/awb-cache",
        *mounts,
        image,
        "python3",
        "-c",
        "from awb.cli import cli; cli()",
        *cli_args,
        "--inside-container",
    ]


def launch_container(*, timeout: int | None = None, **kwargs) -> int:
    """Run Docker without forwarding the host environment or home directory."""
    container_name = f"awb-{uuid.uuid4().hex[:12]}"
    command = build_container_command(container_name=container_name, **kwargs)
    try:
        return subprocess.run(command, check=False, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 124
    except FileNotFoundError as exc:
        raise RuntimeError("Docker is required for --container-image") from exc


def resolve_image_identity(image: str) -> str:
    """Return Docker's immutable local image ID for the manifest."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Id}}", image],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Cannot inspect container image {image!r}") from exc
    identity = result.stdout.strip()
    if result.returncode != 0 or not identity.startswith("sha256:"):
        raise RuntimeError(f"Cannot resolve immutable identity for container image {image!r}")
    return identity
