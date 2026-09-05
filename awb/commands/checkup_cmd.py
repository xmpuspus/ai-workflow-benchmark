"""checkup command, stage 0 promise extraction + stage 1 probe + verdict report.

`awb checkup` is the harness-design instrument (design doc:
docs/superpowers/plans/2026-07-23-awb-v16-harness-design-score.md). Stage 0
parses the harness's instruction and hook files for testable promises
(verification gates, scope rules, ...) for free and instantly. Stage 1 runs a
small probe of real tasks and proves which of those promises actually held.
Exit code contract is documented once in awb/commands/_shared.py's module
docstring; this command returns 0 clean / 1 real finding / 2 tool failure.

awb.harness.promises / awb.harness.integrity are a parallel work package and
are imported lazily (inside functions) so this module, and its test suite,
load fine before that package lands.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.markup import escape
from rich.table import Table

from awb.commands._shared import (
    BAD,
    INFO,
    MUTED,
    OK,
    WARN,
    bar,
    console,
    emit_json,
    save_last_run,
    score_style,
)

TOOL = "claude-code-custom"
VANILLA_TOOL = "claude-code-vanilla"
CODEX_TOOL = "codex-cli"
CHECKUP_TOOLS = (TOOL, CODEX_TOOL)

# The published task-set size, for the "n/100 tasks" honesty line in the
# report header (awb validate / CLAUDE.md: 100 tasks across 8 categories).
_FULL_SUITE_SIZE = 100

_PILLAR_LABELS = {
    "verification_discipline": "verification discipline",
    "scope_discipline": "scope discipline",
    "efficiency": "efficiency",
}

_VERDICT_COLOR = {"HELD": OK, "ENFORCED": OK, "BROKEN": BAD, "UNTESTED": MUTED}


def _probe_confidence(n_tasks: int, full_suite_size: int = _FULL_SUITE_SIZE) -> str:
    """Confidence that an n-task probe represents the full published suite.

    Deliberately not _shared.confidence_label: that answers "how much do I
    trust one capability's score from n task results" (n=8 -> "med").
    This answers "how much does an n-task probe tell me about the 100-task
    suite" - the design doc's header is explicit that the standard 8-task
    fast-check probe should read "low".
    """
    if n_tasks >= full_suite_size * 0.5:
        return "high"
    if n_tasks >= full_suite_size * 0.15:
        return "med"
    return "low"


class _ToolFailureError(Exception):
    """Stage-1 setup could not proceed (auth, adapter, empty task set).

    Caught once in checkup() and mapped to exit 2 - distinct from a clean
    run that simply found a problem (exit 1).
    """


# ----- Stage 0: promise extraction ------------------------------------------


def _has_structural_error(inventory) -> bool:
    return any(i.severity == "error" for i in inventory.structural_issues)


def _render_stage0_text(inventory) -> None:
    errors = [i for i in inventory.structural_issues if i.severity == "error"]
    warns = [i for i in inventory.structural_issues if i.severity == "warn"]

    console.print(
        f"\n[bold]Harness Structure[/bold]  {len(inventory.files_scanned)} file(s) scanned"
    )

    by_pattern: dict[str, list] = {}
    for p in inventory.promises:
        by_pattern.setdefault(p.pattern, []).append(p)

    if by_pattern:
        console.print(f"\n[bold]Promise Inventory[/bold] ({len(inventory.promises)} rule(s))")
        for pattern in sorted(by_pattern):
            console.print(f"  [{INFO}]{pattern}[/{INFO}]")
            for p in by_pattern[pattern]:
                tag = OK if p.enforcement == "hook" else MUTED
                # p.enforcement goes inside the style span, not in its own
                # brackets - a literal "[prose]" would parse as a second
                # (invalid) Rich markup tag and get silently dropped.
                # p.text is raw CLAUDE.md/AGENTS.md/hook-command text the tool
                # doesn't control, so it must be escaped before it reaches
                # Rich's markup parser (rule text mentioning "[bold]" or a
                # copy-pasted "[skip ci]" would otherwise crash or restyle).
                console.print(
                    f"    [{tag}]{p.enforcement}[/{tag}]  {escape(p.text[:80])}  "
                    f"({p.source}:{p.line})"
                )
    else:
        console.print(f"\n[{MUTED}]No testable promises found[/{MUTED}]")

    if errors or warns:
        console.print("\n[bold]Structural Issues[/bold]")
        # i.message can embed a hook command/path token pulled out of the
        # target's own settings.json - untrusted, must be escaped.
        for i in errors:
            console.print(f"  [{BAD}]ERROR[/{BAD}] {escape(i.message)}  ({i.source})")
        for i in warns:
            console.print(f"  [{WARN}]WARN[/{WARN}]  {escape(i.message)}  ({i.source})")
    else:
        console.print(f"\n[{MUTED}]No structural issues[/{MUTED}]")

    if inventory.unparsed_rules:
        console.print(
            f"\n[{MUTED}]{len(inventory.unparsed_rules)} rule(s) not checkable yet "
            f"(unrecognized pattern, not scored)[/{MUTED}]"
        )


# ----- Stage 1: probe setup ---------------------------------------------------


def _load_probe_tasks(tasks_dir: Path | None) -> list:
    from awb.core.fast_check import select_fast_check_tasks
    from awb.core.task_loader import load_all_tasks

    all_tasks = load_all_tasks(tasks_dir=tasks_dir)
    tasks = select_fast_check_tasks(all_tasks)
    if not tasks:
        raise _ToolFailureError("No tasks available to probe")
    return tasks


def _preflight(adapter, label: str) -> str | None:
    try:
        if not adapter.check_available():
            return f"Adapter '{label}' is not available in this environment"
    except NotImplementedError:
        return f"Adapter '{label}' is a stub, not yet implemented"
    if adapter.supports_auth_check():
        ok, msg = adapter.check_auth()
        if not ok:
            return msg
    return None


def _baseline_tool(tool: str) -> str:
    return VANILLA_TOOL if tool == TOOL else f"{tool}-baseline"


def _build_and_preflight_adapters(
    config_dir: Path,
    paired: bool,
    tool: str = TOOL,
    baseline_config_dir: Path | None = None,
):
    from awb.adapters.registry import get_adapter

    try:
        base = get_adapter(tool)
    except ValueError as exc:
        raise _ToolFailureError(str(exc)) from exc
    custom_adapter = type(base)(config_dir=config_dir)
    err = _preflight(custom_adapter, tool)
    if err:
        raise _ToolFailureError(err)

    vanilla_adapter = None
    if paired:
        if tool == TOOL:
            try:
                vanilla_adapter = get_adapter(VANILLA_TOOL)
            except ValueError as exc:
                raise _ToolFailureError(str(exc)) from exc
        else:
            if baseline_config_dir is None:
                raise _ToolFailureError(
                    "Codex paired checkup needs --baseline-config-dir pointing to a separate "
                    "authenticated CODEX_HOME."
                )
            vanilla_adapter = type(base)(config_dir=baseline_config_dir)
        err = _preflight(vanilla_adapter, _baseline_tool(tool))
        if err:
            raise _ToolFailureError(err)
    return custom_adapter, vanilla_adapter


def _run_probe(tool: str, adapter, tasks, tasks_dir: Path | None, concurrency: int):
    """Run one probe pass through BenchmarkRunner, same class run.py uses.

    The adapter is built with --config-dir already applied (run.py has no
    such flag, so it always builds its own adapter from the bare tool name -
    injecting the pre-built instance afterward, the way awb ab already does
    for --config-a/--config-b, is the only way to thread it through).
    """
    from awb.core.runner import BenchmarkRunner

    runner = BenchmarkRunner(
        tool=tool, tasks=tasks, runs=1, concurrency=concurrency, tasks_dir=tasks_dir
    )
    runner._adapter = adapter
    results = asyncio.run(runner.run_all())
    run_dir = runner.recorder.results_dir / f"{runner._run_id}_run1"
    return results, run_dir


def _grade_probe(results, run_dir: Path, task_defs: dict) -> dict[str, list]:
    """Grade every result's trace, bucketed by rubric name.

    A result with no trace, an absent trace file, or a span-less trace
    contributes nothing (never a faked 0 or 100), mirrors
    awb/analysis/prescriptions.py's _grade_traces.
    """
    from awb.trace.grader import grade_trace_or_none

    rubric_scores: dict[str, list] = {}
    for r in results:
        if not r.trace_path:
            continue
        trace_path = run_dir / r.trace_path
        if not trace_path.exists():
            continue
        task = task_defs.get(r.task_id)
        files_to_examine = task.files_to_examine if task else []
        allowed_edit_paths = getattr(r, "allowed_edit_paths", None) or []
        scores = grade_trace_or_none(
            trace_path,
            files_to_examine=files_to_examine,
            allowed_edit_paths=allowed_edit_paths,
        )
        if scores is None:
            continue
        for name, score in scores.items():
            rubric_scores.setdefault(name, []).append(score)
    return rubric_scores


def _source_was_loaded(source: str, loaded_files: list[str]) -> bool:
    normalized = source.replace("\\", "/").lstrip("./")
    for candidate in loaded_files:
        loaded = candidate.replace("\\", "/").lstrip("./")
        if loaded == normalized or loaded.endswith(f"/{normalized}"):
            return True
        if normalized.endswith(f"/{loaded}"):
            return True
    return False


def _rule_verdicts_with_provenance(inventory, results, run_dir, task_defs, rule_integrity):
    """Grade each promise only on attempts that recorded loading its source."""
    from copy import copy

    verdicts = []
    for promise in inventory.promises:
        eligible = [
            result
            for result in results
            if _source_was_loaded(
                promise.source, getattr(result, "loaded_instruction_files", None) or []
            )
        ]
        if not eligible:
            verdict = rule_integrity(inventory, {})
            match = next(v for v in verdict if v.promise is promise)
            match.status = "UNTESTED"
            match.evidence = "rule source was not recorded as loaded for any attempt"
            verdicts.append(match)
            continue
        one_promise = copy(inventory)
        one_promise.promises = [promise]
        scores = _grade_probe(eligible, run_dir, task_defs)
        verdicts.extend(rule_integrity(one_promise, scores))
    return verdicts


# ----- Pillar / rule-integrity / verdict computation --------------------------


def _mean(values: list) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 1)


def _compute_pillars(rubric_scores: dict) -> dict:
    """Verification/scope from the 4 existing rubrics; efficiency from the 2
    new ones (context_discipline, tool_call_efficiency) when present. A
    pillar with no data is None ("not measured"), never imputed as 0."""
    efficiency_values = rubric_scores.get("context_discipline", []) + rubric_scores.get(
        "tool_call_efficiency", []
    )
    return {
        "verification_discipline": _mean(rubric_scores.get("ran_verification_after_change", [])),
        "scope_discipline": _mean(rubric_scores.get("no_out_of_scope_edits", [])),
        "efficiency": _mean(efficiency_values),
    }


def _rule_stats(verdicts: list) -> dict:
    """testable = every verdict except UNTESTED; held = HELD + ENFORCED."""
    testable = [v for v in verdicts if v.status != "UNTESTED"]
    held = [v for v in testable if v.status in ("HELD", "ENFORCED")]
    broken = [v for v in testable if v.status == "BROKEN"]
    return {
        "held": len(held),
        "testable": len(testable),
        "broken": len(broken),
        "untested": len(verdicts) - len(testable),
    }


def _compute_exit_code(pillars: dict, rule_stats: dict, structural_error: bool) -> int:
    measured = [v for v in pillars.values() if v is not None]
    if not measured and rule_stats.get("testable", 0) == 0:
        # The probe verified nothing: every trace ungradeable and no rule
        # testable. That is a measurement failure, not a clean harness, and
        # cron/CI must not read it as one.
        return 2
    any_broken = rule_stats.get("broken", 0) > 0
    any_low = any(v is not None and v < 50 for v in pillars.values())
    return 1 if (structural_error or any_broken or any_low) else 0


def _verdict_sentence(pillars: dict, rule_stats: dict, n_tasks: int) -> str:
    """One plain-language sentence naming the best pillar, the worst pillar,
    and the rule-integrity count (design doc: "Verdict: your harness verifies
    its work (100) but breaks its own scope rule ...")."""
    measured = {k: v for k, v in pillars.items() if v is not None}
    testable = rule_stats.get("testable", 0)
    rule_clause = (
        "no testable rules"
        if testable == 0
        else f"{rule_stats['held']}/{testable} stated rules held"
    )

    if not measured:
        return f"Verdict: no pillar was measurable from {n_tasks} probe task(s), and {rule_clause}."

    best_key = max(measured, key=measured.get)
    worst_key = min(measured, key=measured.get)
    if best_key == worst_key:
        return (
            f"Verdict: {_PILLAR_LABELS[best_key]} is the only measured pillar, at "
            f"{measured[best_key]:.0f}, and {rule_clause}."
        )
    return (
        f"Verdict: {_PILLAR_LABELS[best_key]} is strongest at {measured[best_key]:.0f}, "
        f"{_PILLAR_LABELS[worst_key]} is weakest at {measured[worst_key]:.0f}, "
        f"and {rule_clause}."
    )


# ----- Top fixes: prescriptions + rule-integrity escalations -----------------


def _hook_snippet(promise) -> str:
    """A short, concrete settings.json hook the BROKEN prose rule could
    become. Verification/test-shaped rules gate on Stop (the agent tries to
    finish); everything else gates on PreToolUse (before an edit happens)."""
    pattern = (getattr(promise, "pattern", "") or "").lower()
    if "verif" in pattern or "test" in pattern:
        return (
            "{\n"
            '  "hooks": {\n'
            '    "Stop": [\n'
            '      {"hooks": [{"type": "command", "command": "scripts/require_tests_green.sh"}]}\n'
            "    ]\n"
            "  }\n"
            "}"
        )
    return (
        "{\n"
        '  "hooks": {\n'
        '    "PreToolUse": [\n'
        '      {"matcher": "Edit|Write", "hooks": '
        '[{"type": "command", "command": "scripts/enforce_rule.sh"}]}\n'
        "    ]\n"
        "  }\n"
        "}"
    )


def _escalations(verdicts: list) -> list:
    """Each BROKEN prose rule becomes a prescription: convert it to a hook.

    A BROKEN hook-enforced rule is excluded, it is already a hook, there is
    nothing to convert. Severity uses the probe-wide BROKEN count (per-rule
    violation counts aren't available from RuleVerdict.evidence, which is
    free-form text) so a harness with several broken promises surfaces them
    above a single 2-task rubric hit.
    """
    from awb.analysis.prescriptions import Prescription

    broken = [v for v in verdicts if v.status == "BROKEN"]
    prose_broken = [v for v in broken if getattr(v.promise, "enforcement", "") == "prose"]
    if not prose_broken:
        return []

    severity = len(broken)
    out = []
    for v in prose_broken:
        text = (getattr(v.promise, "text", "") or "rule").strip()
        pattern = getattr(v.promise, "pattern", "rule")
        out.append(
            Prescription(
                id=f"rule-integrity:{pattern}",
                trigger=f"rule-integrity:{text[:40]}",
                evidence=[v.evidence],
                affected_tasks=[],
                severity=severity,
                snippet=_hook_snippet(v.promise),
                rationale=(
                    f'"{text}" is stated as prose but was broken in the probe '
                    f"({v.evidence}). Convert it to a PreToolUse/Stop hook."
                ),
            )
        )
    return out


def _fix_sort_key(p) -> tuple[bool, float, int]:
    """Rank measured deficits separately from the raw affected-task count."""
    deficit = getattr(p, "observed_deficit", None)
    return (deficit is not None, deficit or 0, p.severity)


def _rank_fixes(prescriptions: list, verdicts: list) -> list:
    combined = list(prescriptions) + _escalations(verdicts)
    combined.sort(key=_fix_sort_key, reverse=True)
    return combined[:3]


# ----- Stage 1 + 2: report rendering ------------------------------------------


def _render_stage1_text(
    tool, n_tasks, pillars, rule_stats, verdicts, lift_report, top_fixes, verdict_line
):
    console.print(
        f"\n[bold]Harness Design Report[/bold]  "
        f"{tool}, {n_tasks}/{_FULL_SUITE_SIZE} selected tasks, exploratory"
    )
    console.print(
        f"[{MUTED}]This hand-picked probe describes these tasks only; "
        f"it does not estimate full-suite performance.[/{MUTED}]"
    )
    console.print(verdict_line)
    console.print()

    for key, label in _PILLAR_LABELS.items():
        score = pillars.get(key)
        if score is None:
            console.print(f"  {label:<24} [{MUTED}]{bar(None)}[/{MUTED}]  not measured")
        else:
            style = score_style(score)
            console.print(f"  {label:<24} [{style}]{bar(score)}[/{style}]  {score:5.1f}")

    if rule_stats["testable"] == 0:
        console.print(f"  {'rule integrity':<24} [{MUTED}]no testable rules[/{MUTED}]")
    else:
        ri_pct = rule_stats["held"] / rule_stats["testable"] * 100
        ri_style = score_style(ri_pct)
        console.print(
            f"  {'rule integrity':<24} "
            f"[{ri_style}]{rule_stats['held']}/{rule_stats['testable']}[/{ri_style}]"
            f"  ({rule_stats['untested']} untested)"
        )

    if lift_report is not None:
        sign = "+" if lift_report.lift >= 0 else ""
        color = OK if lift_report.lift > 0 else (BAD if lift_report.lift < 0 else MUTED)
        p_str = f"p={lift_report.p_value:.3f}" if lift_report.p_value is not None else "n/a"
        console.print(
            f"\n  Workflow lift  [{color}]{sign}{lift_report.lift:.1f} pts[/{color}]  ({p_str})"
        )
        if not lift_report.comparison_eligible:
            console.print(
                f"  [{MUTED}]inconclusive: unequal repeat coverage for "
                f"{', '.join(lift_report.incomplete_tasks)}[/{MUTED}]"
            )

    if verdicts:
        table = Table(title="Rule Integrity", header_style="bold")
        table.add_column("Rule")
        table.add_column("Enforcement")
        table.add_column("Evidence")
        table.add_column("Verdict")
        for v in verdicts:
            text = escape((getattr(v.promise, "text", "") or "")[:60])
            enforcement = getattr(v.promise, "enforcement", "")
            color = _VERDICT_COLOR.get(v.status, MUTED)
            table.add_row(text, enforcement, v.evidence, f"[{color}]{v.status}[/{color}]")
        console.print(table)

    if top_fixes:
        console.print("\n[bold]Top fixes[/bold] (ranked by observed deficits)")
        for i, fix in enumerate(top_fixes, 1):
            deficit = getattr(fix, "observed_deficit", None)
            deficit_str = f"  observed deficit {deficit:.0f} pts" if deficit is not None else ""
            # A rule-integrity escalation's rationale embeds the broken
            # promise's own text (see _escalations); a prescriptions.py
            # rationale is a fixed string with nothing to escape either way.
            console.print(f"  {i}. {escape(fix.rationale)}{deficit_str}")
        console.print(
            f"[{MUTED}]Observed deficits do not predict improvement. "
            f"Run each proposed comparison to measure lift.[/{MUTED}]"
        )


@click.command()
@click.option(
    "--tool",
    type=click.Choice(CHECKUP_TOOLS),
    default=TOOL,
    show_default=True,
    help="Configured coding harness to inspect and probe.",
)
@click.option(
    "--static-only", is_flag=True, help="Stage 0 only: promise extraction, zero spend, CI-safe."
)
@click.option("--paired", is_flag=True, help="Also run the vanilla arm and report Workflow Lift.")
@click.option(
    "--config-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Harness config dir to inspect and run with (default: ~/.claude or ~/.codex).",
)
@click.option(
    "--baseline-config-dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Separate authenticated CODEX_HOME for a paired Codex baseline run.",
)
@click.option(
    "--repo-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Repo dir to inspect for structural checks (default: current directory).",
)
@click.option(
    "--tasks-dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Load probe tasks from a custom directory instead of the packaged ones.",
)
@click.option(
    "-j", "--concurrency", type=int, default=4, show_default=True, help="Max parallel probe tasks."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits the full checkup payload as a JSON document on stdout.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip the real-spend confirmation prompt.")
@click.option(
    "--from-run",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Re-grade a saved run dir through the full report instead of running a new probe. "
    "Zero adapter calls, zero spend: rubric changes, task-scope fixes, and harness-file "
    "edits re-measure for free against recorded traces.",
)
def checkup(
    tool: str,
    static_only: bool,
    paired: bool,
    config_dir: str | None,
    baseline_config_dir: str | None,
    repo_dir: str | None,
    tasks_dir: str | None,
    concurrency: int,
    fmt: str,
    yes: bool,
    from_run: str | None,
):
    """Grade a coding-agent harness with static checks and a small real-task probe.

    Exit code contract (see awb/commands/_shared.py): 0 clean, 1 a real
    finding (BROKEN rule, structural error, or a measured pillar below 50),
    2 a tool/environment failure (auth, adapter, or setup crash).
    """
    if from_run and (static_only or paired):
        raise click.UsageError(
            "--from-run re-grades a saved run; it cannot combine with --static-only or --paired"
        )

    if baseline_config_dir and (not paired or tool != CODEX_TOOL):
        raise click.UsageError("--baseline-config-dir is only valid with --tool codex-cli --paired")
    if paired and tool == CODEX_TOOL and not baseline_config_dir:
        raise click.UsageError(
            "--tool codex-cli --paired requires --baseline-config-dir for a separate "
            "authenticated CODEX_HOME"
        )

    default_config_name = ".codex" if tool == CODEX_TOOL else ".claude"
    config_dir_path = Path(config_dir) if config_dir else Path.home() / default_config_name
    baseline_config_dir_path = Path(baseline_config_dir) if baseline_config_dir else None
    repo_dir_path = Path(repo_dir) if repo_dir else Path.cwd()

    from awb.harness.promises import extract_promises

    inventory = extract_promises(config_dir_path, repo_dir_path)
    structural_error = _has_structural_error(inventory)

    if static_only:
        if fmt == "json":
            emit_json({"stage": "static-only", "tool": tool, "inventory": inventory})
        else:
            _render_stage0_text(inventory)
        sys.exit(1 if structural_error else 0)

    if fmt == "text":
        _render_stage0_text(inventory)

    tasks_dir_path = Path(tasks_dir) if tasks_dir else None
    lift_report = None

    if from_run:
        # Free re-grade of a recorded run: no adapter, no prompt, no spend, so
        # JSON mode needs no --yes here.
        from awb.core.results import ResultRecorder
        from awb.core.task_loader import load_all_tasks

        custom_run_dir = Path(from_run)
        try:
            custom_results = ResultRecorder().load_run(custom_run_dir)
            task_defs = {t.id: t for t in load_all_tasks(tasks_dir=tasks_dir_path)}
        except Exception as exc:  # noqa: BLE001 - a bad run dir is a tool failure, not a finding
            console.print(f"[{BAD}]checkup --from-run failed to load the run: {exc}[/{BAD}]")
            sys.exit(2)
        if not custom_results:
            console.print(f"[{BAD}]No results found in {custom_run_dir}[/{BAD}]")
            sys.exit(2)
        n_tasks = len(custom_results)
    else:
        # Pure input validation first: nothing below this line may cost anything
        # until the user's intent is confirmed. The adapter preflight is a real
        # `claude` subprocess call (the v1.5.4 --dry-run lesson), so it runs only
        # after flag validation AND the spend confirmation.
        if fmt == "json" and not yes:
            raise click.UsageError(
                "checkup --format json needs --yes (no interactive prompt in JSON mode)"
            )

        try:
            tasks = _load_probe_tasks(tasks_dir_path)
        except Exception as exc:  # noqa: BLE001 - any setup/load crash is a tool failure
            console.print(f"[{BAD}]checkup setup failed: {exc}[/{BAD}]")
            sys.exit(2)

        n_probe = len(tasks) * (2 if paired else 1)
        if not yes:
            est_low, est_high = n_probe * 0.25, n_probe * 0.5
            console.print(
                f"\nAbout to run {n_probe} real task execution(s) via [bold]{tool}[/bold]"
                f" (est. ~${est_low:.0f}-${est_high:.0f})"
            )
            if not click.confirm("Proceed?", default=True):
                console.print(f"[{MUTED}]Aborted.[/{MUTED}]")
                sys.exit(0)

        try:
            custom_adapter, vanilla_adapter = _build_and_preflight_adapters(
                config_dir_path,
                paired,
                tool=tool,
                baseline_config_dir=baseline_config_dir_path,
            )
        except _ToolFailureError as exc:
            console.print(f"[{BAD}]{exc}[/{BAD}]")
            sys.exit(2)
        except Exception as exc:  # noqa: BLE001 - any setup/load crash is a tool failure
            console.print(f"[{BAD}]checkup setup failed: {exc}[/{BAD}]")
            sys.exit(2)

        custom_results, custom_run_dir = _run_probe(
            tool, custom_adapter, tasks, tasks_dir_path, concurrency
        )
        save_last_run(custom_run_dir)

        task_defs = {t.id: t for t in tasks}
        n_tasks = len(tasks)

        if paired:
            vanilla_results, _vanilla_run_dir = _run_probe(
                _baseline_tool(tool), vanilla_adapter, tasks, tasks_dir_path, concurrency
            )
            from awb.scoring.workflow_lift import compute_workflow_lift

            lift_report = compute_workflow_lift(vanilla_results, custom_results, task_defs)

    rubric_scores = _grade_probe(custom_results, custom_run_dir, task_defs)

    from awb.harness.integrity import rule_integrity

    if from_run:
        verdicts = rule_integrity(inventory, {})
        for verdict in verdicts:
            verdict.status = "UNTESTED"
            verdict.evidence = "retrospective regrade does not prove the current rule was loaded"
    else:
        verdicts = _rule_verdicts_with_provenance(
            inventory, custom_results, custom_run_dir, task_defs, rule_integrity
        )
    pillars = _compute_pillars(rubric_scores)
    rule_stats = _rule_stats(verdicts)

    from awb.analysis.prescriptions import build_prescriptions

    presc_report = build_prescriptions(custom_results, task_defs, custom_run_dir)
    top_fixes = _rank_fixes(presc_report.prescriptions, verdicts)

    verdict_line = _verdict_sentence(pillars, rule_stats, n_tasks)
    exit_code = _compute_exit_code(pillars, rule_stats, structural_error)

    if fmt == "json":
        emit_json(
            {
                "tool": tool,
                "n_tasks": n_tasks,
                "inventory": inventory,
                "pillars": pillars,
                "rule_integrity": rule_stats,
                "verdicts": verdicts,
                "workflow_lift": lift_report,
                "sampling": {
                    "design": "exploratory_hand_picked",
                    "population_inference": False,
                    "n_selected_tasks": n_tasks,
                },
                "rule_attribution": (
                    "retrospective_unverified" if from_run else "recorded_loaded_inputs"
                ),
                "prescriptions": top_fixes,
                "verdict": verdict_line,
                "exit_code": exit_code,
            }
        )
        sys.exit(exit_code)

    _render_stage1_text(
        tool, n_tasks, pillars, rule_stats, verdicts, lift_report, top_fixes, verdict_line
    )
    sys.exit(exit_code)
