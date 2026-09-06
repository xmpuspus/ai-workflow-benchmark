"""Build a conservative GitHub Pages index from exported baseline files."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any


def _text(value: object, fallback: str = "Not recorded") -> str:
    return str(value) if isinstance(value, str) and value else fallback


def _load_baselines(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    baselines = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load baseline {path.name}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("submission"), dict):
            raise ValueError(f"Baseline {path.name} has no submission metadata")
        if not isinstance(payload.get("results"), list):
            raise ValueError(f"Baseline {path.name} has no result list")
        baselines.append((path, payload))
    return baselines


def _row(path: Path, payload: dict[str, Any]) -> str:
    submission = payload["submission"]
    tool = submission.get("tool", {})
    model = submission.get("model", {})
    readiness = submission.get("readiness", {})
    if not isinstance(tool, dict):
        tool = {}
    if not isinstance(model, dict):
        model = {}
    readiness_value = readiness.get("composite") if isinstance(readiness, dict) else None
    readiness_text = (
        f"{readiness_value} (reported, legacy)"
        if isinstance(readiness_value, int | float)
        else "Not recorded"
    )
    values = (
        f'<a href="baselines/{html.escape(path.name)}">{html.escape(path.name)}</a>',
        _text(tool.get("name")),
        _text(tool.get("version")),
        _text(model.get("name")),
        _text(submission.get("awb_version")),
        str(len(payload["results"])),
        readiness_text,
    )
    return (
        "<tr>"
        + "".join(
            f"<td>{html.escape(value) if index else value}</td>"
            for index, value in enumerate(values)
        )
        + "</tr>"
    )


def build_site(baselines_dir: Path, output_dir: Path, static_dir: Path) -> Path:
    """Write one rendered, unranked index and copy explicit public evidence files."""
    baselines = _load_baselines(baselines_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_baselines = output_dir / "baselines"
    output_baselines.mkdir(exist_ok=True)
    for path, _ in baselines:
        shutil.copy2(path, output_baselines / path.name)
    output_static = output_dir / "static"
    shutil.copytree(static_dir, output_static, dirs_exist_ok=True)
    rows = "".join(_row(path, payload) for path, payload in baselines)
    body = rows or '<tr><td colspan="7">No public baselines have been published.</td></tr>'
    page = "\n".join(
        (
            "<!doctype html>",
            '<html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>AWB published baselines</title>",
            '<link rel="stylesheet" href="static/style.css"></head>',
            "<body><header><h1>AI Workflow Benchmark</h1>",
            '<p class="subtitle">Published baseline evidence</p></header>',
            '<main class="container">',
            "<p>These exported baselines are visible for inspection. They are legacy evidence and ",
            "are not ranked or treated as comparable cohorts.</p>",
            "<table><thead><tr><th>Baseline</th><th>Tool</th><th>Tool version</th>",
            "<th>Model</th><th>AWB version</th><th>Tasks</th><th>Readiness</th>",
            "</tr></thead><tbody>",
            body,
            "</tbody></table>",
            "<p>Reported readiness values come from the exported baseline. They do not establish ",
            "current measurement coverage or a comparative ranking.</p>",
            (
                '<p><a href="https://github.com/xmpuspus/ai-workflow-benchmark/blob/main/'
                'METHODOLOGY.md">Methodology</a></p></main></body></html>'
            ),
        )
    )
    index = output_dir / "index.html"
    index.write_text(page)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--static", type=Path, required=True)
    args = parser.parse_args()
    build_site(args.baselines, args.out, args.static)


if __name__ == "__main__":
    main()
