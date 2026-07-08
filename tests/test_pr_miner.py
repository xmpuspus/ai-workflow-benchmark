"""Tests for mining a benchmark task from a merged GitHub PR. All gh calls are mocked."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from awb.core.pr_miner import (
    PrMinerError,
    build_partial_credit,
    infer_languages,
    mine_task_from_pr,
    parse_pr_url,
    resolve_premerge_sha,
    split_test_and_source_files,
)
from awb.core.task_loader import validate_task_yaml

MERGE_SHA = "1234567890abcdef1234567890abcdef1234567"
PREMERGE_SHA = "abcdef1234567890abcdef1234567890abcdef1"


def _fake_gh_run(responses: dict[str, object]):
    """subprocess.run stand-in that answers `gh api <path> ...` from a fixed table."""

    def _run(cmd, capture_output=True, text=True, timeout=30.0):
        assert cmd[0] == "gh"
        assert cmd[1] == "api"
        path = cmd[2]
        if path not in responses:
            raise AssertionError(f"No fake gh response registered for: {path}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(responses[path]), stderr="")

    return _run


@pytest.fixture
def pr_responses():
    return {
        "repos/acme/widgets/pulls/42": {
            "number": 42,
            "title": "Add rate limiting to the checkout API",
            "body": "Adds a token bucket rate limiter.\n<!-- test plan -->\nTested locally.",
            "merged": True,
            "merge_commit_sha": MERGE_SHA,
            "html_url": "https://github.com/acme/widgets/pull/42",
        },
        f"repos/acme/widgets/commits/{MERGE_SHA}": {
            "sha": MERGE_SHA,
            "parents": [{"sha": PREMERGE_SHA}],
        },
        "repos/acme/widgets/pulls/42/files": [
            {"filename": "src/ratelimit/bucket.py"},
            {"filename": "src/ratelimit/__init__.py"},
            {"filename": "tests/test_bucket.py"},
        ],
    }


class TestParsePrUrl:
    def test_valid_url_returns_owner_repo_number(self):
        assert parse_pr_url("https://github.com/acme/widgets/pull/42") == ("acme", "widgets", 42)

    def test_valid_url_with_trailing_path_returns_owner_repo_number(self):
        assert parse_pr_url("https://github.com/acme/widgets/pull/42/files") == (
            "acme",
            "widgets",
            42,
        )

    def test_non_github_url_raises(self):
        with pytest.raises(PrMinerError):
            parse_pr_url("https://example.com/acme/widgets/pull/42")

    def test_non_pr_github_url_raises(self):
        with pytest.raises(PrMinerError):
            parse_pr_url("https://github.com/acme/widgets/issues/42")

    def test_garbage_raises(self):
        with pytest.raises(PrMinerError):
            parse_pr_url("not a url")


class TestSplitTestAndSourceFiles:
    def test_splits_tests_directory_files_as_test(self):
        test_files, source_files = split_test_and_source_files(
            ["tests/test_bucket.py", "src/ratelimit/bucket.py"]
        )
        assert test_files == ["tests/test_bucket.py"]
        assert source_files == ["src/ratelimit/bucket.py"]

    def test_splits_test_prefixed_basename_as_test(self):
        test_files, source_files = split_test_and_source_files(["pkg/test_helpers.py"])
        assert test_files == ["pkg/test_helpers.py"]
        assert source_files == []

    def test_splits_test_suffixed_basename_as_test(self):
        test_files, source_files = split_test_and_source_files(["pkg/helpers_test.go"])
        assert test_files == ["pkg/helpers_test.go"]
        assert source_files == []

    def test_splits_spec_and_dot_test_basename_as_test(self):
        test_files, source_files = split_test_and_source_files(
            ["web/button.spec.js", "web/button.test.tsx"]
        )
        assert test_files == ["web/button.spec.js", "web/button.test.tsx"]
        assert source_files == []

    def test_regular_source_file_is_not_test(self):
        test_files, source_files = split_test_and_source_files(["README.md", "src/app.py"])
        assert test_files == []
        assert source_files == ["README.md", "src/app.py"]


class TestInferLanguages:
    def test_infers_python(self):
        assert infer_languages(["src/module.py"]) == ["python"]

    def test_infers_multiple_unique_languages_in_order(self):
        assert infer_languages(["a.py", "b.ts", "c.py", "d.go"]) == ["python", "typescript", "go"]

    def test_falls_back_to_python_when_no_known_extension(self):
        assert infer_languages(["README.md", "Makefile"]) == ["python"]


class TestBuildPartialCredit:
    def test_points_sum_to_100(self):
        credit = build_partial_credit(
            "python -m pytest",
            "python -m pytest tests/test_bucket.py",
            ["src/ratelimit/bucket.py"],
            ["tests/test_bucket.py"],
        )
        assert sum(c["points"] for c in credit) == 100

    def test_three_criteria(self):
        credit = build_partial_credit("pytest", "pytest tests/", ["src/a.py"], ["tests/a.py"])
        assert len(credit) == 3


class TestResolvePremergeSha:
    def test_returns_first_parent(self, monkeypatch, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        sha = resolve_premerge_sha("acme", "widgets", MERGE_SHA)
        assert sha == PREMERGE_SHA

    def test_raises_when_no_parents(self, monkeypatch):
        responses = {f"repos/o/r/commits/{MERGE_SHA}": {"sha": MERGE_SHA, "parents": []}}
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(responses))
        with pytest.raises(PrMinerError):
            resolve_premerge_sha("o", "r", MERGE_SHA)


class TestMineTaskFromPr:
    def test_unmerged_pr_raises(self, monkeypatch):
        responses = {"repos/acme/widgets/pulls/42": {"number": 42, "title": "WIP", "merged": False}}
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(responses))
        with pytest.raises(PrMinerError, match="only merged PRs"):
            mine_task_from_pr("https://github.com/acme/widgets/pull/42")

    def test_happy_path_builds_expected_task(self, monkeypatch, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr("https://github.com/acme/widgets/pull/42")

        assert mined.premerge_sha == PREMERGE_SHA
        assert mined.merge_commit_sha == MERGE_SHA
        assert mined.test_files == ["tests/test_bucket.py"]
        assert mined.source_files == [
            "src/ratelimit/bucket.py",
            "src/ratelimit/__init__.py",
        ]
        assert mined.task["repo"]["commit"] == PREMERGE_SHA
        assert mined.task["repo"]["url"] == "https://github.com/acme/widgets"
        assert mined.task["label"] == "real_pr"
        assert mined.task["contamination_risk"] == "low"
        assert (
            mined.task["provenance"]["source_pr_url"] == "https://github.com/acme/widgets/pull/42"
        )
        assert sum(c["points"] for c in mined.task["verification"]["partial_credit"]) == 100
        assert "git checkout" in mined.task["repo"]["setup_commands"][-1]

    def test_generated_yaml_passes_validate_task_yaml(self, monkeypatch, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr("https://github.com/acme/widgets/pull/42")
        mined.task["id"] = "FA-901"

        import yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(mined.task, f)
            path = Path(f.name)
        try:
            errors = validate_task_yaml(path)
            assert errors == []
        finally:
            path.unlink()

    def test_contamination_risk_override(self, monkeypatch, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr(
            "https://github.com/acme/widgets/pull/42", contamination_risk="high"
        )
        assert mined.task["contamination_risk"] == "high"

    def test_extra_setup_commands_run_before_overlay(self, monkeypatch, pr_responses):
        monkeypatch.setattr("awb.core.pr_miner.subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr(
            "https://github.com/acme/widgets/pull/42",
            extra_setup_commands=["pip install -e .[dev]"],
        )
        assert mined.task["repo"]["setup_commands"][0] == "pip install -e .[dev]"
        assert "git checkout" in mined.task["repo"]["setup_commands"][1]


class TestOverlayGithubFallback:
    def test_overlay_falls_back_to_github_url(self):
        from awb.core.pr_miner import build_test_overlay_command

        cmd = build_test_overlay_command(
            MERGE_SHA, ["tests/test_x.py"], repo_url="https://github.com/o/r"
        )
        expected = (
            f"git fetch origin {MERGE_SHA} || git fetch https://github.com/o/r {MERGE_SHA} || true"
        )
        assert expected in cmd
        assert cmd.endswith(f"git checkout {MERGE_SHA} -- tests/test_x.py")

    def test_overlay_without_repo_url_fetches_origin_only(self):
        from awb.core.pr_miner import build_test_overlay_command

        cmd = build_test_overlay_command(MERGE_SHA, ["tests/test_x.py"])
        assert "github.com" not in cmd
        assert f"git fetch origin {MERGE_SHA} || true" in cmd

    def test_mined_task_overlay_carries_github_fallback(self, monkeypatch, pr_responses):
        monkeypatch.setattr("subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr("https://github.com/acme/widgets/pull/42")
        overlay = mined.task["repo"]["setup_commands"][-1]
        assert "git fetch https://github.com/acme/widgets" in overlay


class TestSourceOnlyPr:
    def test_mining_pr_with_no_test_files(self, monkeypatch, pr_responses):
        pr_responses["repos/acme/widgets/pulls/42/files"] = [{"filename": "src/app.py"}]
        monkeypatch.setattr("subprocess.run", _fake_gh_run(pr_responses))
        mined = mine_task_from_pr("https://github.com/acme/widgets/pull/42")
        assert mined.test_files == []
        assert all("git checkout" not in c for c in mined.task["repo"]["setup_commands"])
        # No test paths to scope to: the verification command stays bare.
        assert mined.task["verification"]["test_commands"] == ["python -m pytest"]
        pts = sum(c["points"] for c in mined.task["verification"]["partial_credit"])
        assert pts == 100
        touched = mined.task["verification"]["partial_credit"][-1]["check"]
        assert "src" in touched
