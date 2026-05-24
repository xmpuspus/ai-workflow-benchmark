#!/usr/bin/env python3
"""Backfill provenance, contamination_risk, and label on every task YAML.

The v1.2 schema added these fields but no task populated them, leaving the
"trust" framing structural-only. This script stamps reasonable defaults so
the provenance story is real data the leaderboard can actually use.

Heuristic:
  contamination_risk: high for the 5 OSS source repos AWB targets (FastAPI,
    httpx, Flask, Click, Starlette). All five are large, popular, and
    overwhelmingly in any frontier model's training corpus.
  label: synthetic_overlay for hand-crafted tasks against real repos
    (default). Override per-task to real_pr or fresh when applicable.
  provenance.created_at: earliest commit timestamp for the YAML file from
    `git log --diff-filter=A --follow --format=%aI`.
  provenance.last_verified_at: file mtime in ISO format.

Run from repo root:
    python3 scripts/backfill_provenance.py            # dry run
    python3 scripts/backfill_provenance.py --apply    # write changes
"""

from __future__ import annotations

import argparse
import datetime as _dt
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "awb" / "tasks"

PROVENANCE_BLOCK_MARKER = "# === provenance (backfilled) ==="


def file_created_at(path: Path) -> str:
    """Return ISO timestamp of the file's first commit, falling back to mtime."""
    try:
        out = subprocess.check_output(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--follow",
                "--format=%aI",
                "--reverse",
                "--",
                str(path),
            ],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
        if out:
            return out.splitlines()[0]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    mtime = _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.UTC)
    return mtime.isoformat()


def file_mtime_iso(path: Path) -> str:
    return _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.UTC).isoformat()


def already_has_provenance(text: str) -> bool:
    return any(
        line.startswith(("provenance:", "contamination_risk:", "label:"))
        for line in text.splitlines()
    )


def build_block(created_at: str, last_verified_at: str) -> str:
    return (
        f"\n{PROVENANCE_BLOCK_MARKER}\n"
        f"provenance:\n"
        f'  created_at: "{created_at}"\n'
        f'  last_verified_at: "{last_verified_at}"\n'
        f"contamination_risk: high\n"
        f"label: synthetic_overlay\n"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = p.parse_args()

    yaml_files = sorted(TASKS_DIR.rglob("*.yaml"))
    yaml_files = [y for y in yaml_files if not y.name.startswith("_")]
    print(f"Found {len(yaml_files)} task YAMLs under {TASKS_DIR}")

    to_change: list[Path] = []
    for path in yaml_files:
        text = path.read_text()
        if already_has_provenance(text):
            continue
        to_change.append(path)

    print(f"Need backfill: {len(to_change)}")
    if not to_change:
        return 0

    for path in to_change:
        rel = path.relative_to(REPO_ROOT)
        created_at = file_created_at(path)
        last_verified_at = file_mtime_iso(path)
        block = build_block(created_at, last_verified_at)
        if args.apply:
            with open(path, "a") as f:
                f.write(block)
            print(f"  + {rel}")
        else:
            print(f"  (dry) {rel}  created_at={created_at}")

    if not args.apply:
        print("\nRe-run with --apply to write changes.")
        return 0

    print(f"\nBackfilled {len(to_change)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
