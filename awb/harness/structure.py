"""Static structural checks over Claude Code and Codex harness files.

Zero model calls, zero task runs: every check here is a file-existence or
JSON-parse check. This is what backs stage 0 of `awb checkup` - the free,
instant signal a user gets before any tokens are spent.
"""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path

CLAUDE_MD_NAME = "CLAUDE.md"
AGENTS_MD_NAME = "AGENTS.md"
AGENTS_OVERRIDE_NAME = "AGENTS.override.md"
SETTINGS_NAME = "settings.json"
HOOKS_NAME = "hooks.json"
CONFIG_TOML_NAME = "config.toml"

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


def _read_text(path: Path | None) -> tuple[str | None, bool]:
    """Read a file's text, returning (text, had_decode_error).

    A non-UTF-8 file (a common artifact of a Windows-1252 copy-paste from
    Word/Docs) falls back to errors="replace" instead of crashing the whole
    static check; had_decode_error lets the caller surface a structural warn.
    """
    if path is None or not path.exists():
        return None, False
    try:
        return path.read_text(), False
    except OSError:
        return None, False
    except UnicodeDecodeError:
        try:
            return path.read_text(errors="replace"), True
        except OSError:
            return None, False


def _utf8_issue(source: str) -> StructuralIssue:
    return StructuralIssue(severity="warn", message="file is not valid UTF-8", source=source)


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


def _expand_project_dir(token: str, repo_dir: Path | None) -> str:
    """Expand $CLAUDE_PROJECT_DIR to the repo being checked.

    Real Claude Code settings.json hook commands commonly use this env var
    for portability (e.g. "$CLAUDE_PROJECT_DIR/.claude/hooks/check.sh"), and
    it always names the project root, never config_dir.
    """
    if repo_dir is not None and "$CLAUDE_PROJECT_DIR" in token:
        return token.replace("$CLAUDE_PROJECT_DIR", str(repo_dir))
    return token


def _resolve(token: str, base: Path, repo_dir: Path | None = None) -> Path:
    token = _expand_project_dir(token, repo_dir)
    expanded = Path(token).expanduser()
    if expanded.is_absolute():
        return expanded
    return base / expanded


def _check_json_file(
    config_dir: Path | None, filename: str
) -> tuple[list[StructuralIssue], dict | None]:
    issues: list[StructuralIssue] = []
    settings_path = config_dir / filename if config_dir else None
    text, decode_error = _read_text(settings_path)
    if decode_error:
        issues.append(_utf8_issue(_display("config", filename)))
    if text is None:
        return issues, None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        issues.append(
            StructuralIssue(
                severity="error",
                message=f"{filename} is not valid JSON: {exc}",
                source=_display("config", filename),
            )
        )
        return issues, None

    return issues, data if isinstance(data, dict) else None


def _check_settings_json(config_dir: Path | None) -> tuple[list[StructuralIssue], dict | None]:
    return _check_json_file(config_dir, SETTINGS_NAME)


def _check_config_toml(config_dir: Path | None) -> tuple[list[StructuralIssue], dict | None]:
    path = config_dir / CONFIG_TOML_NAME if config_dir else None
    if path is None or not path.exists():
        return [], None
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        return [
            StructuralIssue(
                severity="error",
                message=f"config.toml is not valid TOML: {exc}",
                source=_display("config", CONFIG_TOML_NAME),
            )
        ], None
    except OSError:
        return [], None
    return [], data if isinstance(data, dict) else None


def _check_hook_paths(
    config_dir: Path,
    settings_data: dict,
    repo_dir: Path | None = None,
    source_name: str = SETTINGS_NAME,
) -> list[StructuralIssue]:
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
                raw_command = hook.get("command")
                if "command" in hook and not isinstance(raw_command, str):
                    # A present-but-null or wrong-type command (settings.json
                    # hand-edited or generated badly) is malformed, not merely
                    # absent - it must warn rather than silently become "".
                    issues.append(
                        StructuralIssue(
                            severity="warn",
                            message=f"{event} hook command is not a string: {raw_command!r}",
                            source=_display("config", source_name),
                        )
                    )
                    continue
                command = raw_command or ""
                for token in _extract_path_tokens(command):
                    resolved = _resolve(token, config_dir, repo_dir)
                    if not resolved.exists():
                        # A stray "$VARNAME" other than $CLAUDE_PROJECT_DIR
                        # can't be expanded without a real shell environment,
                        # so "doesn't exist" might just mean "can't check" -
                        # degrade to warn instead of claiming a hard error.
                        severity = "warn" if "$" in str(resolved) else "error"
                        issues.append(
                            StructuralIssue(
                                severity=severity,
                                message=f"{event} hook references missing file: {token}",
                                source=_display("config", source_name),
                            )
                        )
    return issues


def _primary_instruction_file(
    config_dir: Path | None, repo_dir: Path | None
) -> tuple[Path | None, str, str]:
    """Return the most specific active Claude/Codex instruction file."""
    for base, label in ((repo_dir, "repo"), (config_dir, "config")):
        if base is None:
            continue
        for name in (AGENTS_OVERRIDE_NAME, AGENTS_MD_NAME, CLAUDE_MD_NAME):
            if (base / name).exists():
                return base / name, label, name
    if repo_dir is not None:
        return None, "repo", CLAUDE_MD_NAME
    if config_dir is not None:
        return None, "config", CLAUDE_MD_NAME
    return None, "repo", CLAUDE_MD_NAME


def _check_claude_md(config_dir: Path | None, repo_dir: Path | None) -> list[StructuralIssue]:
    issues: list[StructuralIssue] = []
    path, label, instruction_name = _primary_instruction_file(config_dir, repo_dir)
    text, decode_error = _read_text(path)
    if decode_error:
        issues.append(_utf8_issue(_display(label, instruction_name)))

    if text is None or not text.strip():
        issues.append(
            StructuralIssue(
                severity="warn",
                message="vanilla harness, nothing to grade statically",
                source=_display(label, instruction_name),
            )
        )
        return issues

    source = _display(label, instruction_name)

    if repo_dir is not None:
        if NPM_TEST_RE.search(text) and not (repo_dir / "package.json").exists():
            issues.append(
                StructuralIssue(
                    severity="warn",
                    message=f"{instruction_name} documents `npm test` but no package.json exists",
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
                        f"{instruction_name} documents pytest but no pyproject.toml/"
                        "pytest.ini/setup.cfg exists"
                    ),
                    source=source,
                )
            )

    base_dir = repo_dir if repo_dir is not None else config_dir
    if base_dir is not None:
        for match in BACKTICK_PATH_RE.finditer(text):
            token = match.group(1)
            # A bare basename (`publish.sh`, `ab.py`) has no single resolvable
            # location; only slashed paths are checkable without guessing.
            if "/" not in token:
                continue
            if not _resolve(token, base_dir).exists():
                issues.append(
                    StructuralIssue(
                        severity="warn",
                        message=f"{instruction_name} references missing file: {token}",
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

    for filename in (SETTINGS_NAME, HOOKS_NAME):
        json_issues, json_data = _check_json_file(config_dir, filename)
        issues.extend(json_issues)
        if config_dir is not None and json_data is not None:
            issues.extend(_check_hook_paths(config_dir, json_data, repo_dir, filename))

    toml_issues, toml_data = _check_config_toml(config_dir)
    issues.extend(toml_issues)
    if config_dir is not None and toml_data is not None:
        issues.extend(_check_hook_paths(config_dir, toml_data, repo_dir, CONFIG_TOML_NAME))

    issues.extend(_check_claude_md(config_dir, repo_dir))

    return issues
