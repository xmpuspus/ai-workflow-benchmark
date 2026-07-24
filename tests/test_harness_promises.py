"""Tests for harness promise extraction (awb/harness/promises.py)."""

from __future__ import annotations

import json
import time

import pytest

from awb.harness.promises import HarnessInventory, HarnessPromise, extract_promises

# One (positive line, negative line) pair per taxonomy pattern. The positive
# line must fire that pattern and no other; the negative line must fire no
# pattern at all (whether or not it lands in unparsed_rules is checked
# separately).
PATTERN_EXAMPLES: dict[str, tuple[str, str]] = {
    "verification_gate": (
        "Run all tests before declaring the task done.",
        "The tests live in tests/ and cover the parser.",
    ),
    "scope_constraint": (
        "Fix only the reported bug, nothing else.",
        "This module handles user scope validation.",
    ),
    "read_before_edit": (
        "Read the tests first before editing any source file.",
        "Read the README for context.",
    ),
    "lint_gate": (
        "Run ruff before committing any change.",
        "Ruff is a fast Python linter.",
    ),
    "test_first": (
        "Write the test first, then implement.",
        "The button turns red then fades.",
    ),
    "commit_hygiene": (
        "Never git add -A, stage explicit paths instead.",
        "We merged 40 PRs this month.",
    ),
    "file_budget": (
        "Keep PRs under 300 lines.",
        "We touched 12 files in this refactor.",
    ),
    "forbidden_path": (
        "Never edit migrations/ directly.",
        "Migrations live under migrations/ and are auto-generated.",
    ),
}


def _write_claude_md(repo_dir, text: str) -> None:
    (repo_dir / "CLAUDE.md").write_text(text)


@pytest.mark.parametrize("pattern", sorted(PATTERN_EXAMPLES))
def test_pattern_positive_match(tmp_path, pattern):
    positive, _ = PATTERN_EXAMPLES[pattern]
    _write_claude_md(tmp_path, f"- {positive}\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    matched = [p for p in inventory.promises if p.pattern == pattern]
    assert len(matched) == 1
    assert matched[0].text == f"- {positive}"
    assert matched[0].enforcement == "prose"
    assert matched[0].source == "repo/CLAUDE.md"
    assert matched[0].line == 1


@pytest.mark.parametrize("pattern", sorted(PATTERN_EXAMPLES))
def test_pattern_negative_no_match(tmp_path, pattern):
    _, negative = PATTERN_EXAMPLES[pattern]
    _write_claude_md(tmp_path, f"- {negative}\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert inventory.promises == []


def test_all_eight_patterns_are_covered():
    assert set(PATTERN_EXAMPLES) == {
        "verification_gate",
        "scope_constraint",
        "read_before_edit",
        "lint_gate",
        "test_first",
        "commit_hygiene",
        "file_budget",
        "forbidden_path",
    }


def test_scope_constraint_and_forbidden_path_do_not_double_match(tmp_path):
    """A path-specific prohibition is forbidden_path, not also scope_constraint."""
    _write_claude_md(tmp_path, "- Never edit migrations/ directly.\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    patterns = [p.pattern for p in inventory.promises]
    assert patterns == ["forbidden_path"]


def test_generic_never_touch_without_a_path_is_scope_constraint(tmp_path):
    """The same prohibition verb without a named path falls back to scope_constraint."""
    _write_claude_md(tmp_path, "- Never touch the shared state without a lock.\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    patterns = [p.pattern for p in inventory.promises]
    assert patterns == ["scope_constraint"]


def test_imperative_line_matching_no_pattern_goes_to_unparsed(tmp_path):
    _write_claude_md(tmp_path, "- Always explain your reasoning before editing.\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert inventory.promises == []
    assert inventory.unparsed_rules == ["- Always explain your reasoning before editing."]


def test_non_imperative_line_is_silently_dropped(tmp_path):
    _write_claude_md(tmp_path, "This module handles user scope validation.\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert inventory.promises == []
    assert inventory.unparsed_rules == []


def test_headers_and_blank_lines_are_ignored(tmp_path):
    _write_claude_md(
        tmp_path,
        "\n## Rules\n\n- Run tests before declaring the task done.\n\n",
    )

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert len(inventory.promises) == 1
    assert inventory.promises[0].line == 4


def test_code_fence_contents_are_not_parsed_as_rules(tmp_path):
    _write_claude_md(
        tmp_path,
        "\n".join(
            [
                "## Example",
                "```bash",
                "run tests before done  # never git add -A",
                "```",
                "- Fix only the reported bug, nothing else.",
            ]
        ),
    )

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert [p.pattern for p in inventory.promises] == ["scope_constraint"]


def test_agents_md_is_scanned_in_repo_dir(tmp_path):
    (tmp_path / "AGENTS.md").write_text("- Keep PRs under 300 lines.\n")

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert len(inventory.promises) == 1
    assert inventory.promises[0].source == "repo/AGENTS.md"


def test_config_dir_claude_md_is_scanned(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "CLAUDE.md").write_text("- Fix only the reported bug, nothing else.\n")

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    assert len(inventory.promises) == 1
    assert inventory.promises[0].source == "config/CLAUDE.md"


def test_files_scanned_lists_only_files_that_exist(tmp_path):
    config_dir = tmp_path / "config"
    repo_dir = tmp_path / "repo"
    config_dir.mkdir()
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("- Fix only the reported bug, nothing else.\n")
    # No AGENTS.md, no config CLAUDE.md, no settings.json.

    inventory = extract_promises(config_dir=config_dir, repo_dir=repo_dir)

    assert inventory.files_scanned == ["repo/CLAUDE.md"]


def test_both_dirs_none_returns_empty_inventory():
    inventory = extract_promises(config_dir=None, repo_dir=None)

    assert inventory == HarnessInventory(
        promises=[],
        structural_issues=inventory.structural_issues,
        files_scanned=[],
        unparsed_rules=[],
    )
    assert inventory.promises == []
    assert inventory.files_scanned == []


def test_hook_promise_matching_a_pattern_is_enforcement_hook(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "run ruff before commit"}],
                }
            ]
        }
    }
    (config_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    assert len(inventory.promises) == 1
    promise = inventory.promises[0]
    assert isinstance(promise, HarnessPromise)
    assert promise.pattern == "lint_gate"
    assert promise.enforcement == "hook"
    assert promise.source == "config/settings.json"
    assert promise.text == "run ruff before commit"
    assert promise.line >= 1


def test_hook_with_no_pattern_match_goes_to_unparsed_with_hook_prefix(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "python3 hooks/scoped_rules.py"}],
                }
            ]
        }
    }
    (config_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    assert inventory.promises == []
    assert len(inventory.unparsed_rules) == 1
    assert inventory.unparsed_rules[0].startswith("hook:")
    assert "PostToolUse" in inventory.unparsed_rules[0]


def test_hook_command_non_string_does_not_crash(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": 42}]}]
        }
    }
    (config_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    assert inventory.promises == []
    assert any("hook command is not a string" in i.message for i in inventory.structural_issues)


def test_hook_command_null_does_not_crash(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": None}]}]
        }
    }
    (config_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    # Present-but-null is malformed, not absent - the merged structural_issues
    # (sourced from check_structure) must carry the same warn as the 42 case.
    assert inventory.promises == []
    assert any("hook command is not a string" in i.message for i in inventory.structural_issues)


def test_malformed_settings_json_does_not_crash_and_yields_no_hook_promises(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text("{not valid json")

    inventory = extract_promises(config_dir=config_dir, repo_dir=None)

    assert inventory.promises == []
    # The parse failure is a structural issue, not a silently dropped promise.
    assert any(issue.severity == "error" for issue in inventory.structural_issues)


def test_non_utf8_claude_md_does_not_crash(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(
        b"- Run all tests before declaring the task done.\nCaf\xe9 is not ASCII.\n"
    )

    inventory = extract_promises(config_dir=None, repo_dir=tmp_path)

    assert any(p.pattern == "verification_gate" for p in inventory.promises)
    assert any("not valid UTF-8" in i.message for i in inventory.structural_issues)


def test_extract_promises_joins_structural_issues(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    # No CLAUDE.md at all anywhere -> structure.py's vanilla-harness warning.

    inventory = extract_promises(config_dir=None, repo_dir=repo_dir)

    assert any(
        issue.message == "vanilla harness, nothing to grade statically"
        for issue in inventory.structural_issues
    )


class TestLongLinePerformance:
    """A single very long CLAUDE.md line must not make --static-only, the
    documented 'zero spend, CI-safe' entry point, hang. PATH_TOKEN_RE's
    unanchored [\\w.\\-]+ backtracking against a slash-free line is O(n^2)."""

    def test_150kb_single_line_extracts_quickly(self, tmp_path):
        line = "Never touch " + ("x" * 150_000) + " in production"
        _write_claude_md(tmp_path, line + "\n")

        start = time.monotonic()
        inventory = extract_promises(config_dir=None, repo_dir=tmp_path)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"took {elapsed:.1f}s - line-length guard not applied"
        assert inventory.promises == []
        assert any("too long" in u for u in inventory.unparsed_rules)


class TestLiveRunRegressions:
    """Cases surfaced by running checkup against a real repo (v1.6.0 integration)."""

    def test_never_edit_outside_scope_is_scope_constraint(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("- Never edit files outside the task scope\n")
        inv = extract_promises(tmp_path, None)
        assert [p.pattern for p in inv.promises] == ["scope_constraint"]

    def test_lint_before_every_commit_is_lint_gate(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("- Run ruff before every commit\n")
        inv = extract_promises(tmp_path, None)
        assert [p.pattern for p in inv.promises] == ["lint_gate"]


class TestRoundTwoDeltaFindings:
    """r2-delta findings 1 and 2: warn dedup and the hook-text length guard."""

    def test_non_utf8_claude_md_warns_exactly_once(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_bytes(b"- Run tests before done \x93smart\x94\n")
        inv = extract_promises(tmp_path, None)
        utf8_warns = [i for i in inv.structural_issues if "not valid UTF-8" in i.message]
        assert len(utf8_warns) == 1

    def test_oversized_hook_command_is_skipped_fast(self, tmp_path):
        import json as _json
        import time

        long_cmd = "Never touch " + "a" * 150_000
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": long_cmd}]}
                ]
            }
        }
        (tmp_path / "settings.json").write_text(_json.dumps(settings))
        start = time.monotonic()
        inv = extract_promises(tmp_path, None)
        assert time.monotonic() - start < 5.0
        assert any("too long" in u for u in inv.unparsed_rules)
