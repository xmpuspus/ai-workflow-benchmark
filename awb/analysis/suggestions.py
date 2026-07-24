"""Rule-based workflow improvement suggestions mapped to failure patterns."""

from __future__ import annotations

# Maps (failure_category, capability) to actionable suggestions.
# Deterministic rules — not LLM-generated — so results are reproducible.
SUGGESTION_RULES: dict[tuple[str, str], list[str]] = {
    ("partial_completion", "framework_knowledge"): [
        "Add framework-specific patterns to your tool's configuration (e.g., CLAUDE.md)",
        "Include API reference snippets for the frameworks tested",
    ],
    ("partial_completion", "code_comprehension"): [
        "Add codebase navigation hints to your workflow",
        "Configure your tool to read existing code before making changes",
    ],
    ("partial_completion", "bug_diagnosis"): [
        "Add debugging methodology (hypothesis enumeration) to tool configuration",
        "Include common bug patterns (dict.get vs None, bare except) in context",
    ],
    ("partial_completion", "multi_file_reasoning"): [
        "Add architectural context or file-relationship maps to reduce exploration time",
        "Configure your tool to analyze imports and dependencies before editing",
    ],
    ("partial_completion", "test_writing"): [
        "Add test-writing guidelines (async fixtures, mock patterns) to configuration",
        "Include examples of the project's test style in tool context",
    ],
    ("partial_completion", "refactoring_discipline"): [
        "Add 'run existing tests before and after changes' as a workflow step",
        "Configure your tool to check for regressions after each edit",
    ],
    ("partial_completion", "security_awareness"): [
        "Add a security checklist (OWASP Top 10) to your tool's context",
        "Include common vulnerability patterns in configuration",
    ],
    ("timeout", "multi_file_reasoning"): [
        "Tool exceeded time limit on a multi-file task",
        "Add architectural hints or file-relationship context to reduce exploration time",
        "Consider configuring max iteration limits to force early convergence",
    ],
    ("timeout", "framework_knowledge"): [
        "Tool timed out, likely exploring unfamiliar API surface",
        "Add framework documentation references to tool context",
    ],
    ("timeout", "bug_diagnosis"): [
        "Tool timed out while debugging, may be exploring wrong hypotheses",
        "Add structured debugging methodology to workflow configuration",
    ],
    ("test_error", "test_writing"): [
        "Tool wrote tests but they fail at runtime",
        "Add async testing patterns (fixtures, setup/teardown) to configuration",
        "Include examples of working test patterns from the target framework",
    ],
    ("test_error", "framework_knowledge"): [
        "Tests fail due to incorrect API usage",
        "Add framework API reference to tool context",
    ],
    ("code_error", "bug_diagnosis"): [
        "Tool misidentified or incompletely fixed the root cause",
        "Add debugging methodology with hypothesis enumeration to configuration",
    ],
    ("code_error", "code_comprehension"): [
        "Tool made incorrect changes due to misunderstanding existing code",
        "Configure tool to read more context around the target code before editing",
    ],
    ("regression_introduced", "refactoring_discipline"): [
        "Tool broke pre-existing tests while applying its change",
        "Add 'run the existing test suite before and after every edit' to workflow",
        "Configure the tool to halt and re-plan when a previously passing test fails",
    ],
    ("regression_introduced", "test_writing"): [
        "Pre-existing tests regressed, likely an unsafe change to shared code paths",
        "Add a pre-edit step that captures the baseline test set, then diffs after",
    ],
    ("no_edits_made", "code_comprehension"): [
        "Tool produced zero file changes, likely got stuck exploring",
        "Reduce ambiguity in the prompt or add explicit pointers to files_to_examine",
        "Lower max_iterations so the tool commits to a change instead of looping on Read",
    ],
    ("no_edits_made", "context_discovery"): [
        "Tool finished without writing any files, search/discovery overran the budget",
        "Provide a more directed entry point or seed file in the workflow descriptor",
    ],
}


def get_suggestions(failure_category: str, capabilities: list[str]) -> list[str]:
    """Get workflow improvement suggestions for a failure pattern."""
    suggestions = []
    seen = set()
    for cap in capabilities:
        key = (failure_category, cap)
        for s in SUGGESTION_RULES.get(key, []):
            if s not in seen:
                suggestions.append(s)
                seen.add(s)
    if not suggestions:
        suggestions.append(f"Review tool configuration for {', '.join(capabilities)} tasks")
    return suggestions
