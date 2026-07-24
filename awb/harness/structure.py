"""Static structural checks over a harness (settings.json + CLAUDE.md).

Zero model calls, zero task runs: every check here is a file-existence or
JSON-parse check. This is what backs stage 0 of `awb checkup` - the free,
instant signal a user gets before any tokens are spent.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

CLAUDE_MD_NAME = "CLAUDE.md"
SETTINGS_NAME = "settings.json"

# Extensions worth checking when CLAUDE.md backtick-references a path. Kept
# narrow on purpose: a bare word in backticks (`ruff`, `pytest`) is usually a
# command, not a file, and flagging those would be noise, not signal.
KNOWN_FILE_EXTENSIONS = (
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "json",
    "yaml",
    "yml",
    "md",
    "sh",
    "toml",
    "cfg",
    "ini",
    "txt",
)
BACKTICK_PATH_RE = re.compile(r"`([\w./\-]+\.(?:" + "|".join(KNOWN_FILE_EXTENSIONS) + r"))`")

NPM_TEST_RE = re.compile(r"\bnpm test\b", re.IGNORECASE)
PYTEST_RE = re.compile(r"\bpytest\b", re.IGNORECASE)
PYTHON_PROJECT_MARKERS = ("pyproject.toml", "pytest.ini", "setup.cfg")


@dataclass
class StructuralIssue:
    severity: str  # "error" | "warn"
    message: str
    source: str


def _display(label: str, name: str) -> str:
    return f"{label}/{name}"


def _read_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        return path.read_text()
    except OSError:
        return None


def _extract_path_tokens(command: str) -> list[str]:
    """Pull filesystem-path-looking tokens out of a hook command string.

    A bare command name (`ruff`, `npm`) is resolved off PATH and can't be
    checked for existence, so only tokens containing a slash are candidates.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return [t for t in tokens if "/" in t and not t.startswith("-")]


def _resolve(token: str, base: Path) -> Path:
    expanded = Path(token).expanduser()
    if expanded.is_absolute():
        return expanded
    return base / expanded


def _check_settings_json(config_dir: Path | None) -> tuple[list[StructuralIssue], dict | None]:
    issues: list[StructuralIssue] = []
    settings_path = config_dir / SETTINGS_NAME if config_dir else None
    text = _read_text(settings_path)
    if text is None:
        return issues, None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        issues.append(
            StructuralIssue(
                severity="error",
                message=f"settings.json is not valid JSON: {exc}",
                source=_display("config", SETTINGS_NAME),
            )
        )
        return issues, None

    return issues, data if isinstance(data, dict) else None


def _check_hook_paths(config_dir: Path, settings_data: dict) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    hooks = settings_data.get("hooks", {})
    if not isinstance(hooks, dict):
        return issues

    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command", "")
                for token in _extract_path_tokens(command):
                    if not _resolve(token, config_dir).exists():
                        issues.append(
                            StructuralIssue(
                                severity="error",
                                message=f"{event} hook references missing file: {token}",
                                source=_display("config", SETTINGS_NAME),
                            )
                        )
    return issues


def _primary_claude_md(config_dir: Path | None, repo_dir: Path | None) -> tuple[Path | None, str]:
    """Prefer the repo-level CLAUDE.md: it governs the repo actually being graded."""
    if repo_dir is not None and (repo_dir / CLAUDE_MD_NAME).exists():
        return repo_dir / CLAUDE_MD_NAME, "repo"
    if config_dir is not None and (config_dir / CLAUDE_MD_NAME).exists():
        return config_dir / CLAUDE_MD_NAME, "config"
    if repo_dir is not None:
        return None, "repo"
    if config_dir is not None:
        return None, "config"
    return None, "repo"


def _check_claude_md(config_dir: Path | None, repo_dir: Path | None) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    path, label = _primary_claude_md(config_dir, repo_dir)
    text = _read_text(path)

    if text is None or not text.strip():
        issues.append(
            StructuralIssue(
                severity="warn",
                message="vanilla harness, nothing to grade statically",
                source=_display(label, CLAUDE_MD_NAME),
            )
        )
        return issues

    source = _display(label, CLAUDE_MD_NAME)

    if repo_dir is not None:
        if NPM_TEST_RE.search(text) and not (repo_dir / "package.json").exists():
            issues.append(
                StructuralIssue(
                    severity="warn",
                    message="CLAUDE.md documents `npm test` but no package.json exists",
                    source=source,
                )
            )
        if PYTEST_RE.search(text) and not any(
            (repo_dir / marker).exists() for marker in PYTHON_PROJECT_MARKERS
        ):
            issues.append(
                StructuralIssue(
                    severity="warn",
                    message=(
                        "CLAUDE.md documents pytest but no pyproject.toml/"
                        "pytest.ini/setup.cfg exists"
                    ),
                    source=source,
                )
            )

    base_dir = repo_dir if repo_dir is not None else config_dir
    if base_dir is not None:
        for match in BACKTICK_PATH_RE.finditer(text):
            token = match.group(1)
            if not _resolve(token, base_dir).exists():
                issues.append(
                    StructuralIssue(
                        severity="warn",
                        message=f"CLAUDE.md references missing file: {token}",
                        source=source,
                    )
                )

    return issues


def check_structure(config_dir: Path | None, repo_dir: Path | None) -> list[StructuralIssue]:
    """Run every static structural check and return the combined issue list.

    Order: settings.json parses -> hook paths resolve -> CLAUDE.md presence
    -> documented commands match the repo -> referenced local paths exist.
    A JSON parse failure short-circuits the hook-path check (nothing to
    walk), but every other check still runs independently.
    """
    issues: list[StructuralIssue] = []

    settings_issues, settings_data = _check_settings_json(config_dir)
    issues.extend(settings_issues)
    if config_dir is not None and settings_data is not None:
        issues.extend(_check_hook_paths(config_dir, settings_data))

    issues.extend(_check_claude_md(config_dir, repo_dir))

    return issues
