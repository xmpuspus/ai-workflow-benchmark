"""Tests for `awb checkup` (awb/commands/checkup_cmd.py).

awb.harness.promises / awb.harness.integrity are owned by a parallel agent
and do not exist in this worktree, so every test installs fakes into
sys.modules before invoking the command (checkup_cmd imports them lazily
inside functions, so this works without the real package present).

No real adapter/model calls: BenchmarkRunner is never constructed directly
in these tests - `_run_probe` is monkeypatched exactly like ab_cmd's
`_run_config` in tests/test_ab.py.

The full-probe path calls save_last_run, which writes the relative path
results/.last_run - the autouse _isolated_cwd fixture chdir's into tmp_path
so that never touches the real repo's results/ directory.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import types
from pathlib import Path

import pytest
from click.testing import CliRunner

from awb.adapters.base import ToolAdapter, ToolResult
from awb.core.config import (
    RunCost,
    RunEnvironment,
    RunMetrics,
    RunOutcome,
    RunQuality,
    RunResult,
    TaskConstraints,
    TaskDefinition,
    TaskRepo,
    TaskVerification,
)
from awb.trace import FILE_EDIT, TEST_RUN, TraceWriter, new_span


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# ----- Fake awb.harness install ---------------------------------------------


@dataclasses.dataclass
class _FakeHarnessPromise:
    text: str
    pattern: str
    enforcement: str
    source: str
    line: int


@dataclasses.dataclass
class _FakeStructuralIssue:
    severity: str
    message: str
    source: str


@dataclasses.dataclass
class _FakeHarnessInventory:
    promises: list
    structural_issues: list
    files_scanned: list
    unparsed_rules: list


@dataclasses.dataclass
class _FakeRuleVerdict:
    promise: object
    status: str
    evidence: str


def install_fake_harness(
    monkeypatch,
    promises=(),
    structural_issues=(),
    files_scanned=("CLAUDE.md",),
    unparsed_rules=(),
    status_by_pattern=None,
):
    """Install fake awb.harness.promises / awb.harness.integrity into
    sys.modules. Returns a dict of call-capture lists for assertions."""
    calls = {"extract_args": [], "integrity_args": []}
    status_by_pattern = status_by_pattern or {}

    def extract_promises(config_dir, repo_dir):
        calls["extract_args"].append((config_dir, repo_dir))
        return _FakeHarnessInventory(
            promises=list(promises),
            structural_issues=list(structural_issues),
            files_scanned=list(files_scanned),
            unparsed_rules=list(unparsed_rules),
        )

    def rule_integrity(inventory, rubric_scores):
        calls["integrity_args"].append((inventory, rubric_scores))
        verdicts = []
        for p in inventory.promises:
            status = status_by_pattern.get(p.pattern, "UNTESTED")
            verdicts.append(
                _FakeRuleVerdict(promise=p, status=status, evidence=f"evidence:{p.pattern}")
            )
        return verdicts

    harness_pkg = types.ModuleType("awb.harness")
    promises_mod = types.ModuleType("awb.harness.promises")
    integrity_mod = types.ModuleType("awb.harness.integrity")
    promises_mod.extract_promises = extract_promises
    promises_mod.HarnessPromise = _FakeHarnessPromise
    promises_mod.StructuralIssue = _FakeStructuralIssue
    promises_mod.HarnessInventory = _FakeHarnessInventory
    integrity_mod.rule_integrity = rule_integrity
    integrity_mod.RuleVerdict = _FakeRuleVerdict
    harness_pkg.promises = promises_mod
    harness_pkg.integrity = integrity_mod

    monkeypatch.setitem(sys.modules, "awb.harness", harness_pkg)
    monkeypatch.setitem(sys.modules, "awb.harness.promises", promises_mod)
    monkeypatch.setitem(sys.modules, "awb.harness.integrity", integrity_mod)
    return calls


# ----- Fake adapters ---------------------------------------------------------


class _FakeCustomAdapter(ToolAdapter):
    name = "claude-code-custom"
    display_name = "Fake Custom"
    supports_config_dir = True

    def __init__(self, config_dir=None):
        self.config_dir = config_dir

    async def execute(self, prompt, workspace, max_turns=20, timeout_seconds=1800, on_event=None):
        return ToolResult(success=True)

    def check_available(self):
        return True

    def get_config_hash(self):
        return "hash"

    def supports_auth_check(self):
        return True

    def check_auth(self):
        return True, ""


class _FakeVanillaAdapter(_FakeCustomAdapter):
    name = "claude-code-vanilla"
    supports_config_dir = False


class _UnavailableAdapter(_FakeCustomAdapter):
    def check_available(self):
        return False


class _AuthFailAdapter(_FakeCustomAdapter):
    def check_auth(self):
        return False, "Claude Code is not logged in."


def _fake_get_adapter(custom_cls=_FakeCustomAdapter, vanilla_cls=_FakeVanillaAdapter):
    def _get(name):
        if name == "claude-code-custom":
            return custom_cls()
        if name == "claude-code-vanilla":
            return vanilla_cls()
        raise ValueError(f"Unknown adapter '{name}'")

    return _get


def _make_task(task_id="BF-001", capabilities=None, files_to_examine=None):
    return TaskDefinition(
        id=task_id,
        category="bug-fix",
        title="Test task",
        difficulty="easy",
        estimated_minutes=15,
        languages=["python"],
        repo=TaskRepo(url="https://example.com", commit="abc123"),
        verification=TaskVerification(),
        constraints=TaskConstraints(),
        capabilities=capabilities or ["security_awareness"],
        files_to_examine=files_to_examine or ["src/x.py"],
    )


def _make_result(task_id="BF-001", tool="claude-code-custom", score=80, trace_path=""):
    return RunResult(
        task_id=task_id,
        tool=tool,
        run_id="probe_run1",
        timestamp="2026-01-01T00:00:00Z",
        outcome=RunOutcome(
            success=score == 100, partial_credit_score=score, partial_credit_max=100
        ),
        metrics=RunMetrics(),
        cost=RunCost(),
        quality=RunQuality(),
        environment=RunEnvironment(os="test", hardware="test"),
        trace_path=trace_path,
    )


# ----- Pure helper unit tests -------------------------------------------------


class TestProbeConfidence:
    """Confidence that an n-task probe represents the full published suite -
    a different question from _shared.confidence_label's per-capability
    sample size (which would call n=8 "med"; the design doc's header wants
    the standard 8-task fast-check probe to read "low")."""

    def test_standard_eight_task_probe_reads_low(self):
        from awb.commands.checkup_cmd import _probe_confidence

        assert _probe_confidence(8) == "low"

    def test_half_the_suite_reads_high(self):
        from awb.commands.checkup_cmd import _probe_confidence

        assert _probe_confidence(50) == "high"

    def test_mid_coverage_reads_med(self):
        from awb.commands.checkup_cmd import _probe_confidence

        assert _probe_confidence(20) == "med"


class TestMean:
    def test_empty_is_none(self):
        from awb.commands.checkup_cmd import _mean

        assert _mean([]) is None

    def test_ignores_none_entries(self):
        from awb.commands.checkup_cmd import _mean

        assert _mean([80, None, 60]) == 70.0

    def test_all_none_is_none(self):
        from awb.commands.checkup_cmd import _mean

        assert _mean([None, None]) is None


class TestComputePillars:
    def test_verification_and_scope_from_rubric_scores(self):
        from awb.commands.checkup_cmd import _compute_pillars

        pillars = _compute_pillars(
            {
                "ran_verification_after_change": [100, 0],
                "no_out_of_scope_edits": [100, 100],
            }
        )
        assert pillars["verification_discipline"] == 50.0
        assert pillars["scope_discipline"] == 100.0

    def test_efficiency_not_measured_when_new_rubrics_absent(self):
        from awb.commands.checkup_cmd import _compute_pillars

        pillars = _compute_pillars({"ran_verification_after_change": [100]})
        assert pillars["efficiency"] is None

    def test_efficiency_combines_both_new_rubrics(self):
        from awb.commands.checkup_cmd import _compute_pillars

        pillars = _compute_pillars({"context_discipline": [80, 100], "tool_call_efficiency": [60]})
        assert pillars["efficiency"] == pytest.approx(80.0)

    def test_missing_pillar_is_none_not_zero(self):
        from awb.commands.checkup_cmd import _compute_pillars

        pillars = _compute_pillars({})
        assert pillars["verification_discipline"] is None
        assert pillars["scope_discipline"] is None
        assert pillars["efficiency"] is None


class TestRuleStats:
    def test_counts_by_status(self):
        from awb.commands.checkup_cmd import _rule_stats

        verdicts = [
            _FakeRuleVerdict(promise=None, status="HELD", evidence=""),
            _FakeRuleVerdict(promise=None, status="ENFORCED", evidence=""),
            _FakeRuleVerdict(promise=None, status="BROKEN", evidence=""),
            _FakeRuleVerdict(promise=None, status="UNTESTED", evidence=""),
        ]
        stats = _rule_stats(verdicts)
        assert stats == {"held": 2, "testable": 3, "broken": 1, "untested": 1}

    def test_no_verdicts_means_no_testable_rules(self):
        from awb.commands.checkup_cmd import _rule_stats

        stats = _rule_stats([])
        assert stats["testable"] == 0
        assert stats["held"] == 0


class TestComputeExitCode:
    def test_clean_is_zero(self):
        from awb.commands.checkup_cmd import _compute_exit_code

        pillars = {"verification_discipline": 90.0, "scope_discipline": 80.0, "efficiency": None}
        rule_stats = {"held": 1, "testable": 1, "broken": 0, "untested": 0}
        assert _compute_exit_code(pillars, rule_stats, structural_error=False) == 0

    def test_structural_error_forces_one(self):
        from awb.commands.checkup_cmd import _compute_exit_code

        pillars = {"verification_discipline": 90.0, "scope_discipline": 80.0, "efficiency": None}
        rule_stats = {"held": 1, "testable": 1, "broken": 0, "untested": 0}
        assert _compute_exit_code(pillars, rule_stats, structural_error=True) == 1

    def test_broken_rule_forces_one(self):
        from awb.commands.checkup_cmd import _compute_exit_code

        pillars = {"verification_discipline": 90.0, "scope_discipline": 80.0, "efficiency": None}
        rule_stats = {"held": 0, "testable": 1, "broken": 1, "untested": 0}
        assert _compute_exit_code(pillars, rule_stats, structural_error=False) == 1

    def test_low_pillar_forces_one(self):
        from awb.commands.checkup_cmd import _compute_exit_code

        pillars = {"verification_discipline": 40.0, "scope_discipline": 80.0, "efficiency": None}
        rule_stats = {"held": 1, "testable": 1, "broken": 0, "untested": 0}
        assert _compute_exit_code(pillars, rule_stats, structural_error=False) == 1

    def test_pillar_exactly_50_does_not_fire(self):
        from awb.commands.checkup_cmd import _compute_exit_code

        pillars = {"verification_discipline": 50.0, "scope_discipline": 80.0, "efficiency": None}
        rule_stats = {"held": 1, "testable": 1, "broken": 0, "untested": 0}
        assert _compute_exit_code(pillars, rule_stats, structural_error=False) == 0


class TestVerdictSentence:
    def test_names_best_and_worst_pillar_and_rule_count(self):
        from awb.commands.checkup_cmd import _verdict_sentence

        pillars = {"verification_discipline": 100.0, "scope_discipline": 40.0, "efficiency": None}
        rule_stats = {"held": 5, "testable": 7, "broken": 2, "untested": 1}
        line = _verdict_sentence(pillars, rule_stats, n_tasks=8)
        assert "verification discipline is strongest at 100" in line
        assert "scope discipline is weakest at 40" in line
        assert "5/7 stated rules held" in line

    def test_single_measured_pillar_does_not_claim_a_comparison(self):
        from awb.commands.checkup_cmd import _verdict_sentence

        pillars = {"verification_discipline": 90.0, "scope_discipline": None, "efficiency": None}
        rule_stats = {"held": 0, "testable": 0, "broken": 0, "untested": 3}
        line = _verdict_sentence(pillars, rule_stats, n_tasks=8)
        assert "verification discipline" in line
        assert "90" in line
        assert "no testable rules" in line

    def test_no_measured_pillars_still_returns_a_sentence(self):
        from awb.commands.checkup_cmd import _verdict_sentence

        pillars = {"verification_discipline": None, "scope_discipline": None, "efficiency": None}
        rule_stats = {"held": 0, "testable": 0, "broken": 0, "untested": 0}
        line = _verdict_sentence(pillars, rule_stats, n_tasks=8)
        assert "Verdict" in line
        assert "no testable rules" in line


class TestRankFixes:
    def test_sorts_by_severity_descending_and_caps_at_three(self):
        from awb.analysis.prescriptions import Prescription
        from awb.commands.checkup_cmd import _rank_fixes

        prescriptions = [
            Prescription(
                id="a",
                trigger="t",
                evidence=[],
                affected_tasks=[],
                severity=2,
                snippet="## A\n",
                rationale="a",
            ),
            Prescription(
                id="b",
                trigger="t",
                evidence=[],
                affected_tasks=[],
                severity=5,
                snippet="## B\n",
                rationale="b",
            ),
            Prescription(
                id="c",
                trigger="t",
                evidence=[],
                affected_tasks=[],
                severity=3,
                snippet="## C\n",
                rationale="c",
            ),
            Prescription(
                id="d",
                trigger="t",
                evidence=[],
                affected_tasks=[],
                severity=1,
                snippet="## D\n",
                rationale="d",
            ),
        ]
        top = _rank_fixes(prescriptions, verdicts=[])
        assert [p.id for p in top] == ["b", "c", "a"]

    def test_prefers_estimated_score_delta_when_present(self):
        from awb.analysis.prescriptions import Prescription
        from awb.commands.checkup_cmd import _rank_fixes

        low_severity_high_delta = Prescription(
            id="low-sev",
            trigger="t",
            evidence=[],
            affected_tasks=[],
            severity=1,
            snippet="## X\n",
            rationale="x",
        )
        low_severity_high_delta.estimated_score_delta = 20
        high_severity_no_delta = Prescription(
            id="high-sev",
            trigger="t",
            evidence=[],
            affected_tasks=[],
            severity=10,
            snippet="## Y\n",
            rationale="y",
        )
        top = _rank_fixes([high_severity_no_delta, low_severity_high_delta], verdicts=[])
        assert top[0].id == "low-sev"

    def test_delta_bearing_item_outranks_higher_severity_no_delta_item(self):
        """estimated_score_delta (a points scale) and severity (a raw broken-
        rule count) are not the same unit; sorting -delta against -severity
        in one key would let a severity=10 no-delta item outrank a delta=1
        item. A single comparable key (has_delta, delta, severity) must
        always rank delta-bearing items first, regardless of magnitude."""
        from awb.analysis.prescriptions import Prescription
        from awb.commands.checkup_cmd import _rank_fixes

        small_delta = Prescription(
            id="small-delta",
            trigger="t",
            evidence=[],
            affected_tasks=[],
            severity=1,
            snippet="## A\n",
            rationale="a",
            estimated_score_delta=1.0,
        )
        large_severity_no_delta = Prescription(
            id="large-severity",
            trigger="t",
            evidence=[],
            affected_tasks=[],
            severity=10,
            snippet="## B\n",
            rationale="b",
        )
        top = _rank_fixes([large_severity_no_delta, small_delta], verdicts=[])
        assert top[0].id == "small-delta"

    def test_broken_scope_rule_escalates_with_pretooluse_snippet(self):
        """_hook_snippet picks the PreToolUse-shaped snippet unless the
        pattern name contains 'verif' or 'test' - a scope_constraint promise
        takes the else branch. An `in ... or in ...` assertion would pass
        either way (or if the branches were swapped); pin the actual branch."""
        from awb.commands.checkup_cmd import _rank_fixes

        promise = _FakeHarnessPromise(
            text="never edit files outside scope",
            pattern="scope_constraint",
            enforcement="prose",
            source="CLAUDE.md",
            line=12,
        )
        verdicts = [_FakeRuleVerdict(promise=promise, status="BROKEN", evidence="violated 3/8")]
        top = _rank_fixes([], verdicts)
        assert len(top) == 1
        assert "PreToolUse" in top[0].snippet
        assert "Stop" not in top[0].snippet
        assert "hook" in top[0].rationale.lower()

    def test_broken_verification_rule_escalates_with_stop_snippet(self):
        """The 'verif'/'test' substring branch: a verification_gate promise
        must get the Stop-shaped snippet, not PreToolUse."""
        from awb.commands.checkup_cmd import _rank_fixes

        promise = _FakeHarnessPromise(
            text="run tests before declaring done",
            pattern="verification_gate",
            enforcement="prose",
            source="CLAUDE.md",
            line=9,
        )
        verdicts = [_FakeRuleVerdict(promise=promise, status="BROKEN", evidence="violated 2/8")]
        top = _rank_fixes([], verdicts)
        assert len(top) == 1
        assert "Stop" in top[0].snippet
        assert "PreToolUse" not in top[0].snippet
        assert "hook" in top[0].rationale.lower()

    def test_broken_hook_enforced_rule_does_not_escalate(self):
        """A hook-enforced rule that broke is already a hook - nothing to convert."""
        from awb.commands.checkup_cmd import _rank_fixes

        promise = _FakeHarnessPromise(
            text="lint before commit",
            pattern="lint_gate",
            enforcement="hook",
            source="settings.json",
            line=3,
        )
        verdicts = [_FakeRuleVerdict(promise=promise, status="BROKEN", evidence="hook failed once")]
        top = _rank_fixes([], verdicts)
        assert top == []

    def test_held_rule_does_not_escalate(self):
        from awb.commands.checkup_cmd import _rank_fixes

        promise = _FakeHarnessPromise(
            text="run tests before done",
            pattern="verification_gate",
            enforcement="prose",
            source="CLAUDE.md",
            line=5,
        )
        verdicts = [_FakeRuleVerdict(promise=promise, status="HELD", evidence="fired 8/8")]
        top = _rank_fixes([], verdicts)
        assert top == []


# ----- CLI: --static-only against the REAL awb.harness package ---------------
# Every test above/below this section installs a fake awb.harness.promises/
# integrity into sys.modules. That fake's dataclass shapes happen to match
# the real ones field-for-field, but nothing enforces that going forward - a
# future rename or field addition in promises.py would leave every faked
# test green while the real CLI path broke. These tests import the real
# awb.harness package instead, so the wiring itself is under test.


class TestCheckupStaticOnlyRealHarness:
    def test_promise_inventory_and_clean_exit(self, tmp_path):
        from awb.commands.checkup_cmd import checkup

        config_dir = tmp_path / "config"
        repo_dir = tmp_path / "repo"
        config_dir.mkdir()
        repo_dir.mkdir()
        (repo_dir / "CLAUDE.md").write_text("- Run all tests before declaring the task done.\n")

        result = CliRunner().invoke(
            checkup,
            [
                "--static-only",
                "--config-dir",
                str(config_dir),
                "--repo-dir",
                str(repo_dir),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Promise Inventory" in result.output
        assert "verification_gate" in result.output
        assert "Run all tests before declaring the task done." in result.output
        assert "No structural issues" in result.output

    def test_structural_error_from_missing_hook_file_exits_one(self, tmp_path):
        from awb.commands.checkup_cmd import checkup

        config_dir = tmp_path / "config"
        repo_dir = tmp_path / "repo"
        config_dir.mkdir()
        repo_dir.mkdir()
        (repo_dir / "CLAUDE.md").write_text("- Fix only the reported bug, nothing else.\n")
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 hooks/does_not_exist.py"}
                        ],
                    }
                ]
            }
        }
        (config_dir / "settings.json").write_text(json.dumps(settings))

        result = CliRunner().invoke(
            checkup,
            [
                "--static-only",
                "--config-dir",
                str(config_dir),
                "--repo-dir",
                str(repo_dir),
            ],
        )

        assert result.exit_code == 1, result.output
        assert "ERROR" in result.output
        assert "hooks/does_not_exist.py" in result.output

    def test_null_hook_command_does_not_crash(self, tmp_path):
        """Regression: a hand-edited settings.json with a null hook command
        used to raise AttributeError before extract_promises() could even
        reach checkup()'s own try/except (structure.py's _extract_path_tokens
        crash, see tests/test_harness_structure.py)."""
        from awb.commands.checkup_cmd import checkup

        config_dir = tmp_path / "config"
        repo_dir = tmp_path / "repo"
        config_dir.mkdir()
        repo_dir.mkdir()
        (repo_dir / "CLAUDE.md").write_text("- Fix only the reported bug, nothing else.\n")
        settings = {
            "hooks": {
                "PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": None}]}]
            }
        }
        (config_dir / "settings.json").write_text(json.dumps(settings))

        result = CliRunner().invoke(
            checkup,
            [
                "--static-only",
                "--config-dir",
                str(config_dir),
                "--repo-dir",
                str(repo_dir),
            ],
        )

        assert result.exit_code == 0, result.output

    def test_full_probe_wires_real_rule_integrity(self, monkeypatch, tmp_path):
        """The full-probe path (rule_integrity(real_inventory, rubric_scores)
        feeding _compute_pillars/_rule_stats/_verdict_sentence/
        _compute_exit_code) with the real awb.harness dataclasses, not the
        fakes every other full-probe test in this file installs. _run_probe
        stays mocked - that boundary is legitimate, no real model call."""
        from awb.commands import checkup_cmd

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (tmp_path / "CLAUDE.md").write_text("- Run all tests before declaring the task done.\n")
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())
        task = _make_task()
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [task])

        run_dir = tmp_path / "probe_run1"
        run_dir.mkdir()
        trace_name = _write_trace(run_dir, task.id, "claude-code-custom", task.files_to_examine)
        result_obj = _make_result(task.id, score=90, trace_path=trace_name)

        def _fake_run_probe(tool, adapter, tasks, tasks_dir, concurrency):
            return [result_obj], run_dir

        monkeypatch.setattr(checkup_cmd, "_run_probe", _fake_run_probe)

        result = CliRunner().invoke(checkup_cmd.checkup, ["--config-dir", str(config_dir), "--yes"])

        assert result.exit_code == 0, result.output
        assert "Rule Integrity" in result.output
        assert "HELD" in result.output


# ----- CLI: --static-only -----------------------------------------------------


class TestCheckupStaticOnly:
    def test_zero_structural_issues_exits_clean(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(monkeypatch, promises=[], structural_issues=[])
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "Harness Structure" in result.output

    def test_structural_error_exits_one(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(
            monkeypatch,
            structural_issues=[
                _FakeStructuralIssue(
                    severity="error", message="bad hook path", source="settings.json"
                )
            ],
        )
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 1, result.output
        assert "bad hook path" in result.output

    def test_structural_warn_does_not_exit_one(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(
            monkeypatch,
            structural_issues=[
                _FakeStructuralIssue(severity="warn", message="unusual pattern", source="CLAUDE.md")
            ],
        )
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_promise_inventory_grouped_by_pattern_with_enforcement_tags(
        self, monkeypatch, tmp_path
    ):
        from awb.commands.checkup_cmd import checkup

        promise = _FakeHarnessPromise(
            text="never touch files outside scope",
            pattern="scope_constraint",
            enforcement="prose",
            source="CLAUDE.md",
            line=9,
        )
        install_fake_harness(monkeypatch, promises=[promise])
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "scope_constraint" in result.output
        assert "prose" in result.output

    def test_unparsed_rules_get_not_checkable_yet_note(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(monkeypatch, unparsed_rules=["some weird custom rule"])
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "not checkable yet" in result.output

    def test_promise_text_with_unbalanced_markup_does_not_crash(self, monkeypatch, tmp_path):
        """A CLAUDE.md line copy-pasted from a PR title ('Fix bug[/x]') must not
        raise rich.errors.MarkupError - the same bug class already fixed once
        for PR-derived text in task_cmd.py (f7cc2bb)."""
        from awb.commands.checkup_cmd import checkup

        promise = _FakeHarnessPromise(
            text="Fix bug[/x] in [red]parser",
            pattern="scope_constraint",
            enforcement="prose",
            source="CLAUDE.md",
            line=3,
        )
        install_fake_harness(monkeypatch, promises=[promise])
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_promise_text_with_balanced_markup_appears_literally(self, monkeypatch, tmp_path):
        """A balanced bracket pair that happens to be a real Rich style name
        must render as literal text, not as live styling that could spoof a
        genuine verdict line."""
        from awb.commands.checkup_cmd import checkup

        promise = _FakeHarnessPromise(
            text="run tests before done [green]spoofed PASS[/green]",
            pattern="verification_gate",
            enforcement="prose",
            source="CLAUDE.md",
            line=7,
        )
        install_fake_harness(monkeypatch, promises=[promise])
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "[green]spoofed PASS[/green]" in result.output

    def test_structural_issue_message_with_markup_does_not_crash(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(
            monkeypatch,
            structural_issues=[
                _FakeStructuralIssue(
                    severity="error",
                    message="hook references missing file: hooks/[legacy].sh",
                    source="settings.json",
                )
            ],
        )
        result = CliRunner().invoke(checkup, ["--static-only", "--config-dir", str(tmp_path)])
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert result.exit_code == 1, result.output
        assert "hooks/[legacy].sh" in result.output

    def test_json_output_is_parseable_and_has_no_probe_keys(self, monkeypatch, tmp_path):
        from awb.commands.checkup_cmd import checkup

        install_fake_harness(monkeypatch)
        result = CliRunner().invoke(
            checkup, ["--static-only", "--format", "json", "--config-dir", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["stage"] == "static-only"
        assert "inventory" in data
        assert "pillars" not in data

    def test_static_only_never_builds_a_runner(self, monkeypatch, tmp_path):
        """Stage 0 must be zero model calls - no BenchmarkRunner construction."""
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)

        def _must_not_run(*args, **kwargs):
            raise AssertionError("probe ran despite --static-only")

        monkeypatch.setattr(checkup_cmd, "_run_probe", _must_not_run)
        result = CliRunner().invoke(
            checkup_cmd.checkup, ["--static-only", "--config-dir", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output


# ----- CLI: full probe (mocked runner + real synthetic traces) --------------


def _write_trace(run_dir: Path, task_id: str, tool: str, files_to_examine: list[str]) -> str:
    name = f"{task_id}_{tool}.trace.jsonl"
    with TraceWriter(run_dir / name) as w:
        w.write(
            new_span(
                FILE_EDIT, attributes={"file.path": files_to_examine[0], "file.action": "write"}
            )
        )
        w.write(new_span(TEST_RUN, attributes={"test.passed": 1, "test.failed": 0}))
    return name


class TestCheckupFullProbe:
    def _base_args(self, tmp_path, extra=()):
        return ["--config-dir", str(tmp_path), "--yes", *extra]

    def test_adapter_unavailable_exits_two(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", _fake_get_adapter(custom_cls=_UnavailableAdapter)
        )
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [_make_task()]
        )
        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 2, result.output

    def test_auth_failure_exits_two(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr(
            "awb.adapters.registry.get_adapter", _fake_get_adapter(custom_cls=_AuthFailAdapter)
        )
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [_make_task()]
        )
        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 2, result.output
        assert "logged in" in result.output.lower()

    def test_load_crash_exits_two_not_one(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())

        def _boom(tasks_dir=None):
            raise RuntimeError("task YAML corrupt")

        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", _boom)
        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 2, result.output

    def test_no_tasks_selected_exits_two(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [])
        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 2, result.output

    def test_json_format_without_yes_is_a_usage_error(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [_make_task()]
        )
        result = CliRunner().invoke(
            checkup_cmd.checkup, ["--config-dir", str(tmp_path), "--format", "json"]
        )
        assert result.exit_code == 2, result.output

    def test_declining_confirmation_aborts_cleanly(self, monkeypatch, tmp_path):
        from awb.commands import checkup_cmd

        install_fake_harness(monkeypatch)
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())
        monkeypatch.setattr(
            "awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [_make_task()]
        )

        def _must_not_run(*args, **kwargs):
            raise AssertionError("probe ran despite declined confirmation")

        monkeypatch.setattr(checkup_cmd, "_run_probe", _must_not_run)
        result = CliRunner().invoke(
            checkup_cmd.checkup, ["--config-dir", str(tmp_path)], input="n\n"
        )
        assert result.exit_code == 0, result.output

    def _happy_path_mocks(
        self, monkeypatch, tmp_path, status_by_pattern=None, structural_issues=(), promise_text=None
    ):
        from awb.commands import checkup_cmd

        promise = _FakeHarnessPromise(
            text=promise_text or "run tests before done",
            pattern="verification_gate",
            enforcement="prose",
            source="CLAUDE.md",
            line=4,
        )
        install_fake_harness(
            monkeypatch,
            promises=[promise],
            structural_issues=structural_issues,
            status_by_pattern=status_by_pattern or {"verification_gate": "HELD"},
        )
        monkeypatch.setattr("awb.adapters.registry.get_adapter", _fake_get_adapter())
        task = _make_task()
        monkeypatch.setattr("awb.core.task_loader.load_all_tasks", lambda tasks_dir=None: [task])

        run_dir = tmp_path / "probe_run1"
        run_dir.mkdir()
        trace_name = _write_trace(run_dir, task.id, "claude-code-custom", task.files_to_examine)
        result_obj = _make_result(task.id, score=90, trace_path=trace_name)

        def _fake_run_probe(tool, adapter, tasks, tasks_dir, concurrency):
            return [result_obj], run_dir

        monkeypatch.setattr(checkup_cmd, "_run_probe", _fake_run_probe)
        return run_dir

    def test_happy_path_exits_zero(self, monkeypatch, tmp_path):
        self._happy_path_mocks(monkeypatch, tmp_path)
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 0, result.output
        assert "Harness Design Report" in result.output
        assert "verification discipline" in result.output

    def test_happy_path_saves_last_run(self, monkeypatch, tmp_path):
        run_dir = self._happy_path_mocks(monkeypatch, tmp_path)
        from awb.commands import checkup_cmd
        from awb.commands._shared import resolve_run_dir

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 0, result.output
        assert resolve_run_dir(None) == run_dir

    def test_broken_rule_exits_one(self, monkeypatch, tmp_path):
        self._happy_path_mocks(
            monkeypatch, tmp_path, status_by_pattern={"verification_gate": "BROKEN"}
        )
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 1, result.output

    def test_structural_error_forces_exit_one_even_with_clean_probe(self, monkeypatch, tmp_path):
        self._happy_path_mocks(
            monkeypatch,
            tmp_path,
            structural_issues=[
                _FakeStructuralIssue(severity="error", message="bad json", source="settings.json")
            ],
        )
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 1, result.output

    def test_rule_integrity_table_rendered_with_verdict_colors(self, monkeypatch, tmp_path):
        self._happy_path_mocks(monkeypatch, tmp_path)
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 0, result.output
        assert "Rule Integrity" in result.output
        assert "HELD" in result.output

    def test_rule_integrity_table_escapes_markup_in_promise_text(self, monkeypatch, tmp_path):
        self._happy_path_mocks(
            monkeypatch, tmp_path, promise_text="run tests before done [green]PASS[/green]"
        )
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 0, result.output
        assert "[green]PASS[/green]" in result.output

    def test_top_fix_escalation_rationale_escapes_promise_text(self, monkeypatch, tmp_path):
        self._happy_path_mocks(
            monkeypatch,
            tmp_path,
            promise_text="run tests before done [red]never[/red]",
            status_by_pattern={"verification_gate": "BROKEN"},
        )
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 1, result.output
        assert "[red]never[/red]" in result.output

    def test_json_format_full_payload_is_parseable(self, monkeypatch, tmp_path):
        self._happy_path_mocks(monkeypatch, tmp_path)
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(
            checkup_cmd.checkup, self._base_args(tmp_path, extra=["--format", "json"])
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        for key in (
            "tool",
            "n_tasks",
            "inventory",
            "pillars",
            "rule_integrity",
            "verdicts",
            "prescriptions",
            "verdict",
        ):
            assert key in data, f"missing key: {key}"
        assert data["workflow_lift"] is None

    def test_paired_runs_vanilla_and_reports_workflow_lift(self, monkeypatch, tmp_path):
        run_dir = self._happy_path_mocks(monkeypatch, tmp_path)
        from awb.commands import checkup_cmd

        task = _make_task()
        vanilla_result = _make_result(task.id, tool="claude-code-vanilla", score=50)
        custom_result = _make_result(task.id, tool="claude-code-custom", score=90)
        call_count = {"n": 0}

        def _fake_run_probe(tool, adapter, tasks, tasks_dir, concurrency):
            call_count["n"] += 1
            if tool == "claude-code-vanilla":
                return [vanilla_result], run_dir
            return [custom_result], run_dir

        monkeypatch.setattr(checkup_cmd, "_run_probe", _fake_run_probe)

        result = CliRunner().invoke(
            checkup_cmd.checkup, self._base_args(tmp_path, extra=["--paired", "--format", "json"])
        )
        assert result.exit_code == 0, result.output
        assert call_count["n"] == 2
        data = json.loads(result.output)
        assert data["workflow_lift"] is not None
        assert data["workflow_lift"]["lift"] == pytest.approx(40.0)

    def test_top_fixes_include_rule_integrity_escalation_when_broken(self, monkeypatch, tmp_path):
        self._happy_path_mocks(
            monkeypatch, tmp_path, status_by_pattern={"verification_gate": "BROKEN"}
        )
        from awb.commands import checkup_cmd

        result = CliRunner().invoke(checkup_cmd.checkup, self._base_args(tmp_path))
        assert result.exit_code == 1, result.output
        assert "Top fixes" in result.output
        assert "not additive" in result.output
