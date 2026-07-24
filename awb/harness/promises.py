"""Extract testable promises out of a harness's CLAUDE.md/AGENTS.md/settings.json.

A "promise" is one rule line matched against a fixed 8-pattern taxonomy
(verification_gate, scope_constraint, read_before_edit, lint_gate, test_first,
commit_hygiene, file_budget, forbidden_path). Detection is deliberately
precision-over-recall: a rule line that reads as imperative but matches no
pattern is never silently dropped, it goes into `unparsed_rules` so the
report stays honest about what it could not parse. A wrong HELD/BROKEN
verdict downstream costs all trust, and that starts here with not
over-matching.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from awb.harness.structure import StructuralIssue, check_structure

# --- the 8-pattern taxonomy ------------------------------------------------
# Each pattern is a list of compiled, case-insensitive regexes. forbidden_path
# is handled separately (see _is_forbidden_path) because it needs a
# prohibition verb *and* a path-shaped token, not a keyword alone.

PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "verification_gate": [
        re.compile(r"run\b.{0,20}\btests?\b.{0,30}\bbefore\b.{0,20}\bdone\b", re.I),
        re.compile(r"tests?\s+must\s+pass", re.I),
        re.compile(r"run\s+\S+.{0,30}\bafter\s+implement", re.I),
        re.compile(r"\bverify\b.{0,30}\bbefore\s+(?:declaring|marking)\b", re.I),
        re.compile(r"run\b.{0,30}\bbefore\s+(?:declaring|marking)\b.{0,20}\bdone\b", re.I),
    ],
    "scope_constraint": [
        re.compile(r"\bfix only\b", re.I),
        re.compile(r"\bminimal fix\b", re.I),
        re.compile(r"\bdo\s?n['o]?t\s+(?:modify|edit|change)\b", re.I),
        re.compile(r"\bnever\s+(?:touch|edit|modify|change)\b", re.I),
        re.compile(r"\btouch only\b", re.I),
        re.compile(r"\boutside\s+(?:the\s+)?(?:task\s+)?scope\b", re.I),
    ],
    "read_before_edit": [
        re.compile(r"read\s+(?:the\s+)?tests?\s+first", re.I),
        re.compile(r"read\b.{0,30}\bbefore\s+editing\b", re.I),
    ],
    "lint_gate": [
        re.compile(
            r"\b(?:ruff|eslint|lint(?:er)?)\b.{0,40}"
            r"\bbefore\s+(?:every\s+|each\s+|any\s+)?(?:commit|committing|push|pushing)",
            re.I,
        ),
        re.compile(
            r"before\s+(?:every\s+|each\s+|any\s+)?(?:commit|committing|push|pushing).{0,40}"
            r"\b(?:ruff|eslint|lint(?:er)?)\b",
            re.I,
        ),
    ],
    "test_first": [
        re.compile(r"write\s+(?:the|a)\s+tests?\s+first", re.I),
        re.compile(r"\bTDD\b", re.I),
        re.compile(r"\bred\s+then\s+green\b", re.I),
        re.compile(r"\bred-green\b", re.I),
    ],
    "commit_hygiene": [
        re.compile(r"never\s+git\s+add\s+-a\b", re.I),
        re.compile(r"stage\s+explicit\s+paths", re.I),
        re.compile(r"no\s+force\s+push", re.I),
        re.compile(r"never\s+force\s+push", re.I),
    ],
    "file_budget": [
        re.compile(r"keep\s+prs?\s+under\s+\d+", re.I),
        re.compile(r"touch\s+at\s+most\s+\d+\s+files", re.I),
        re.compile(r"at\s+most\s+\d+\s+files", re.I),
    ],
}

FORBIDDEN_PATH_VERB_RE = re.compile(r"\b(?:never|do\s?n['o]?t)\s+(?:edit|touch|modify)\b", re.I)
PATH_TOKEN_RE = re.compile(r"[`]?[\w.\-]+/[\w.\-/]*[`]?")

# Lines that read as imperative but match none of the 8 patterns still get
# surfaced (never silently dropped). This is a curated verb list, not an NLP
# parser: precision over recall applies here too.
IMPERATIVE_VERBS = {
    "run",
    "never",
    "always",
    "do",
    "don't",
    "write",
    "read",
    "keep",
    "stage",
    "fix",
    "verify",
    "check",
    "ensure",
    "avoid",
    "use",
    "add",
    "remove",
    "delete",
    "test",
    "commit",
    "touch",
    "edit",
    "modify",
    "confirm",
    "validate",
    "apply",
    "stop",
    "revert",
}

BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

# PATH_TOKEN_RE's [\w.\-]+ backtracks O(n^2) against a long slash-free run.
# No legitimate single-line rule needs to be this long - past this it's a
# prose wall (an unwrapped paragraph, a pasted spec block), not a rule.
MAX_RULE_LINE_LENGTH = 2000


@dataclass
class HarnessPromise:
    text: str
    pattern: str
    enforcement: str  # "hook" | "prose"
    source: str
    line: int


@dataclass
class HarnessInventory:
    promises: list[HarnessPromise] = field(default_factory=list)
    structural_issues: list[StructuralIssue] = field(default_factory=list)
    files_scanned: list[str] = field(default_factory=list)
    unparsed_rules: list[str] = field(default_factory=list)


def _is_forbidden_path(line: str) -> bool:
    return bool(FORBIDDEN_PATH_VERB_RE.search(line) and PATH_TOKEN_RE.search(line))


def _match_line(line: str) -> str | None:
    if not line:
        return None
    if _is_forbidden_path(line):
        return "forbidden_path"
    for key, patterns in PATTERNS.items():
        if any(pat.search(line) for pat in patterns):
            return key
    return None


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def _looks_imperative(line: str) -> bool:
    stripped = _strip_bullet(line)
    if not stripped:
        return False
    first_word = re.split(r"[\s:]", stripped, maxsplit=1)[0].strip("*_").rstrip(".,:;").lower()
    return first_word in IMPERATIVE_VERBS


def _iter_rule_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (1-based line number, stripped line) for non-blank, non-header,
    non-code-fence lines. Code fences are skipped so example commands in a
    ```bash``` block never get mistaken for rule prose."""
    in_code_fence = False
    for i, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line or line.startswith("#"):
            continue
        yield i, line


def _utf8_issue(source: str) -> StructuralIssue:
    return StructuralIssue(severity="warn", message="file is not valid UTF-8", source=source)


def _read_text_safe(path: Path) -> tuple[str, bool]:
    """Read a file's text, returning (text, had_decode_error).

    A non-UTF-8 file (a common artifact of a Windows-1252 copy-paste from
    Word/Docs) falls back to errors="replace" instead of crashing
    extract_promises(); had_decode_error lets the caller surface a
    structural warn (mirrors structure.py's _read_text).
    """
    try:
        return path.read_text(), False
    except UnicodeDecodeError:
        return path.read_text(errors="replace"), True


def _extract_from_markdown(
    path: Path, source_label: str
) -> tuple[list[HarnessPromise], list[str], bool]:
    text, decode_error = _read_text_safe(path)
    promises: list[HarnessPromise] = []
    unparsed: list[str] = []
    for line_no, line in _iter_rule_lines(text):
        if len(line) > MAX_RULE_LINE_LENGTH:
            unparsed.append(f"line {line_no} too long, skipped ({len(line)} chars)")
            continue
        key = _match_line(line)
        if key:
            promises.append(
                HarnessPromise(
                    text=line,
                    pattern=key,
                    enforcement="prose",
                    source=source_label,
                    line=line_no,
                )
            )
        elif _looks_imperative(line):
            unparsed.append(line)
    return promises, unparsed, decode_error


def _find_line(raw_text: str, needle: str) -> int:
    if not needle:
        return 1
    idx = raw_text.find(needle)
    if idx == -1:
        return 1
    return raw_text.count("\n", 0, idx) + 1


def _extract_from_hooks(config_dir: Path) -> tuple[list[HarnessPromise], list[str], bool]:
    settings_path = config_dir / "settings.json"
    if not settings_path.exists():
        return [], [], False

    raw_text, decode_error = _read_text_safe(settings_path)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # structure.py already reports the parse error; nothing to extract.
        return [], [], decode_error

    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    if not isinstance(hooks, dict):
        return [], [], decode_error

    promises: list[HarnessPromise] = []
    unparsed: list[str] = []

    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher") or ""
            if not isinstance(matcher, str):
                matcher = ""
            for hook in group.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command") or ""
                if not isinstance(command, str):
                    # Malformed settings.json (e.g. hand-edited); structure.py
                    # already surfaces this shape as a structural warn.
                    continue
                if len(command) > MAX_RULE_LINE_LENGTH or len(matcher) > MAX_RULE_LINE_LENGTH:
                    # Same O(n^2) backtracking exposure as markdown lines;
                    # a hook command this long is not a checkable rule.
                    unparsed.append(
                        f"hook: {event} command too long, skipped ({len(command)} chars)"
                    )
                    continue
                key = _match_line(command) or _match_line(matcher)
                if key:
                    promises.append(
                        HarnessPromise(
                            text=command,
                            pattern=key,
                            enforcement="hook",
                            source="config/settings.json",
                            line=_find_line(raw_text, command),
                        )
                    )
                else:
                    descriptor = f"hook: {event} matcher={matcher!r} command={command}"
                    unparsed.append(descriptor)

    return promises, unparsed, decode_error


def extract_promises(config_dir: Path | None, repo_dir: Path | None) -> HarnessInventory:
    """Scan config_dir's CLAUDE.md/settings.json and repo_dir's CLAUDE.md/AGENTS.md.

    Either argument may be None (e.g. a repo with no `~/.claude` override, or
    a bare config check with no repo checked out yet). Structural issues are
    joined in here too, so one call gives the full stage-0 inventory.
    """
    promises: list[HarnessPromise] = []
    unparsed_rules: list[str] = []
    files_scanned: list[str] = []
    decode_issues: list[StructuralIssue] = []

    if config_dir is not None:
        claude_md = config_dir / "CLAUDE.md"
        if claude_md.exists():
            files_scanned.append("config/CLAUDE.md")
            p, u, bad_utf8 = _extract_from_markdown(claude_md, "config/CLAUDE.md")
            promises.extend(p)
            unparsed_rules.extend(u)
            if bad_utf8:
                decode_issues.append(_utf8_issue("config/CLAUDE.md"))

        settings_path = config_dir / "settings.json"
        if settings_path.exists():
            files_scanned.append("config/settings.json")
            p, u, bad_utf8 = _extract_from_hooks(config_dir)
            promises.extend(p)
            unparsed_rules.extend(u)
            if bad_utf8:
                decode_issues.append(_utf8_issue("config/settings.json"))

    if repo_dir is not None:
        for name, label in (("CLAUDE.md", "repo/CLAUDE.md"), ("AGENTS.md", "repo/AGENTS.md")):
            path = repo_dir / name
            if path.exists():
                files_scanned.append(label)
                p, u, bad_utf8 = _extract_from_markdown(path, label)
                promises.extend(p)
                unparsed_rules.extend(u)
                if bad_utf8:
                    decode_issues.append(_utf8_issue(label))

    structural_issues = check_structure(config_dir, repo_dir)
    structural_issues.extend(decode_issues)
    # structure.py checks the same primary files, so a decode warn (and any
    # future overlapping check) can arrive from both sides; report each once.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[StructuralIssue] = []
    for issue in structural_issues:
        key = (issue.severity, issue.message, issue.source)
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    structural_issues = deduped

    return HarnessInventory(
        promises=promises,
        structural_issues=structural_issues,
        files_scanned=files_scanned,
        unparsed_rules=unparsed_rules,
    )
