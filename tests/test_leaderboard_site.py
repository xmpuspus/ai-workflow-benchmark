from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _builder_module():
    path = Path("scripts/build_leaderboard_site.py")
    spec = importlib.util.spec_from_file_location("build_leaderboard_site", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_site_is_rendered_unranked_and_links_to_copied_evidence(tmp_path):
    baselines, static, output = tmp_path / "baselines", tmp_path / "static", tmp_path / "site"
    baselines.mkdir()
    static.mkdir()
    (static / "style.css").write_text("body{}")
    (baselines / "baseline.json").write_text(
        json.dumps(
            {
                "submission": {
                    "tool": {"name": "tool <unsafe>", "version": "1"},
                    "model": {"name": "model"},
                    "awb_version": "1.7.0",
                    "readiness": {"composite": 86.0},
                },
                "results": [{"task_id": "BF-001"}],
            }
        )
    )

    index = _builder_module().build_site(baselines, output, static)
    page = index.read_text()

    assert "{{" not in page and "{%" not in page
    assert 'href="static/style.css"' in page
    assert 'href="baselines/baseline.json"' in page
    assert 'class="table-wrapper"' in page
    assert 'id="leaderboard-table"' in page
    assert "Scroll the table horizontally" in page
    assert "legacy evidence" in page
    assert "not ranked" in page
    assert "tool &lt;unsafe&gt;" in page
    assert (output / "baselines" / "baseline.json").exists()
