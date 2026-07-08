"""Regression: v1.4.0 added readiness/trace_summary/trace_grade to exports and
baselines but the submission schema still rejected them, so `awb submit`
failed on the repo's own published baseline (caught by the v1.5.0 fresh-venv
smoke)."""

from __future__ import annotations

import json
from pathlib import Path

from awb.submission.ingest import validate_submission

_ROOT = Path(__file__).parent.parent


def _load_baseline():
    path = _ROOT / "results" / "baselines" / "claude-code-custom-1.4.0-fast-check.json"
    return json.loads(path.read_text())


def test_published_baseline_validates():
    errors = validate_submission(_load_baseline())
    assert errors == [], errors


def test_null_trace_grade_validates():
    data = _load_baseline()
    data["results"][0]["runs"][0]["trace_grade"] = None
    assert validate_submission(data) == []


def test_schema_copies_stay_in_sync():
    packaged = json.loads((_ROOT / "awb" / "submission" / "schema.json").read_text())
    repo = json.loads((_ROOT / "results" / "submission-schema.json").read_text())
    assert packaged == repo
