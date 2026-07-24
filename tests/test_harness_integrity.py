"""Tests for rule-integrity verdicts (awb/harness/integrity.py)."""

from __future__ import annotations

import json

from awb.harness.integrity import RuleVerdict, rule_integrity
from awb.harness.promises import HarnessInventory, HarnessPromise, extract_promises
from awb.harness.structure import StructuralIssue


def _promise(
    pattern: str, enforcement: str = "prose", source: str = "repo/CLAUDE.md"
) -> HarnessPromise:
    return HarnessPromise(
        text=f"rule for {pattern}", pattern=pattern, enforcement=enforcement, source=source, line=1
    )


def test_enforced_when_hook_and_structural_check_passed():
    promise = _promise("verification_gate", enforcement="hook", source="config/settings.json")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    [verdict] = rule_integrity(inventory, rubric_scores={})

    assert verdict.status == "ENFORCED"
    assert verdict.evidence == "hook resolves, deterministic"
    assert verdict.promise is promise


def test_hook_falls_through_when_its_structural_check_failed():
    promise = HarnessPromise(
        text="python3 hooks/missing.py",
        pattern="lint_gate",
        enforcement="hook",
        source="config/settings.json",
        line=5,
    )
    issue = StructuralIssue(
        severity="error",
        message="PreToolUse hook references missing file: hooks/missing.py",
        source="config/settings.json",
    )
    inventory = HarnessInventory(promises=[promise], structural_issues=[issue])

    [verdict] = rule_integrity(inventory, rubric_scores={})

    # lint_gate has no mapped rubric, so a broken hook falls through to UNTESTED.
    assert verdict.status == "UNTESTED"
    assert verdict.evidence == "no rubric can observe this yet"


def test_untested_when_pattern_has_no_mapped_rubric():
    for pattern in ("lint_gate", "commit_hygiene", "file_budget"):
        promise = _promise(pattern)
        inventory = HarnessInventory(promises=[promise], structural_issues=[])

        [verdict] = rule_integrity(
            inventory, rubric_scores={"ran_verification_after_change": [90, 91, 92]}
        )

        assert verdict.status == "UNTESTED"
        assert verdict.evidence == "no rubric can observe this yet"


def test_untested_when_no_applicable_task_ran():
    promise = _promise("verification_gate")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    [verdict] = rule_integrity(
        inventory, rubric_scores={"ran_verification_after_change": [None, None]}
    )

    assert verdict.status == "UNTESTED"
    assert verdict.evidence == "no applicable task in this run"


def test_untested_when_rubric_key_absent_entirely():
    promise = _promise("read_before_edit")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    [verdict] = rule_integrity(inventory, rubric_scores={})

    assert verdict.status == "UNTESTED"
    assert verdict.evidence == "no applicable task in this run"


def test_broken_when_two_or_more_violations():
    promise = _promise("scope_constraint")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    scores = [50, 55, 90, 88, 92, 91, 89, 93]
    [verdict] = rule_integrity(inventory, rubric_scores={"no_out_of_scope_edits": scores})

    assert verdict.status == "BROKEN"
    assert verdict.evidence == "violated in 2/8 tasks"


def test_held_when_zero_violations_and_high_mean():
    promise = _promise("verification_gate")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    scores = [90, 95, 100]
    [verdict] = rule_integrity(inventory, rubric_scores={"ran_verification_after_change": scores})

    assert verdict.status == "HELD"
    assert verdict.evidence == "held in 3/3 tasks"


def test_held_allows_exactly_one_violation_if_mean_still_high():
    promise = _promise("verification_gate")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    scores = [50, 80, 90]  # one violation (50), mean = 73.33 >= 70
    [verdict] = rule_integrity(inventory, rubric_scores={"ran_verification_after_change": scores})

    assert verdict.status == "HELD"
    assert verdict.evidence == "held in 2/3 tasks"


def test_untested_weak_signal_when_mean_too_low_for_held():
    promise = _promise("verification_gate")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    scores = [50, 65, 68]  # one violation (50), mean = 61.0 < 70
    [verdict] = rule_integrity(inventory, rubric_scores={"ran_verification_after_change": scores})

    assert verdict.status == "UNTESTED"
    assert verdict.evidence == "signal too weak: mean 61 over 3 tasks"


def test_none_entries_are_excluded_from_the_denominator():
    promise = _promise("verification_gate")
    inventory = HarnessInventory(promises=[promise], structural_issues=[])

    scores = [None, None, 80, 90]
    [verdict] = rule_integrity(inventory, rubric_scores={"ran_verification_after_change": scores})

    assert verdict.status == "HELD"
    assert verdict.evidence == "held in 2/2 tasks"


def test_forbidden_path_and_scope_constraint_share_the_scope_rubric():
    forbidden = _promise("forbidden_path")
    scope = _promise("scope_constraint")
    inventory = HarnessInventory(promises=[forbidden, scope], structural_issues=[])

    scores = [50, 55, 90, 88, 92, 91, 89, 93]
    verdicts = rule_integrity(inventory, rubric_scores={"no_out_of_scope_edits": scores})

    assert [v.status for v in verdicts] == ["BROKEN", "BROKEN"]


def test_read_before_edit_and_test_first_share_the_read_tests_rubric():
    read_first = _promise("read_before_edit")
    tdd = _promise("test_first")
    inventory = HarnessInventory(promises=[read_first, tdd], structural_issues=[])

    scores = [90, 95]
    verdicts = rule_integrity(inventory, rubric_scores={"read_tests_before_edit": scores})

    assert [v.status for v in verdicts] == ["HELD", "HELD"]


def test_verdict_order_and_length_match_promise_order():
    promises = [_promise("verification_gate"), _promise("scope_constraint"), _promise("lint_gate")]
    inventory = HarnessInventory(promises=promises, structural_issues=[])

    verdicts = rule_integrity(inventory, rubric_scores={})

    assert len(verdicts) == 3
    assert [v.promise for v in verdicts] == promises
    assert all(isinstance(v, RuleVerdict) for v in verdicts)


def test_end_to_end_realistic_claude_md_and_settings_json(tmp_path):
    config_dir = tmp_path / "config"
    repo_dir = tmp_path / "repo"
    config_dir.mkdir()
    repo_dir.mkdir()

    (repo_dir / "CLAUDE.md").write_text(
        "\n".join(
            [
                "## Harness Rules",
                "",
                "- Run tests before declaring the task done.",
                "- Never edit migrations/ directly.",
                "- Do not modify files outside the ticket scope.",
                "- Read the tests first before editing any source file.",
                "- Keep PRs under 300 lines.",
                "",
            ]
        )
    )

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

    inventory = extract_promises(config_dir=config_dir, repo_dir=repo_dir)
    by_pattern = {p.pattern: p for p in inventory.promises}
    assert set(by_pattern) == {
        "verification_gate",
        "forbidden_path",
        "scope_constraint",
        "read_before_edit",
        "file_budget",
        "lint_gate",
    }

    n = 8
    rubric_scores = {
        "ran_verification_after_change": [90] * n,
        "no_out_of_scope_edits": [50, 55] + [90] * (n - 2),
        "read_tests_before_edit": [85, 88],
    }

    verdicts = rule_integrity(inventory, rubric_scores)
    verdict_by_pattern = {v.promise.pattern: v for v in verdicts}

    assert verdict_by_pattern["verification_gate"].status == "HELD"
    assert verdict_by_pattern["forbidden_path"].status == "BROKEN"
    assert verdict_by_pattern["scope_constraint"].status == "BROKEN"
    assert verdict_by_pattern["read_before_edit"].status == "HELD"
    assert verdict_by_pattern["file_budget"].status == "UNTESTED"
    assert verdict_by_pattern["file_budget"].evidence == "no rubric can observe this yet"
    assert verdict_by_pattern["lint_gate"].status == "ENFORCED"
    assert verdict_by_pattern["lint_gate"].evidence == "hook resolves, deterministic"
