"""Tests for static harness structure checks (awb/harness/structure.py)."""

from __future__ import annotations

import json

from awb.harness.structure import StructuralIssue, check_structure


def _write_settings(config_dir, hooks: dict) -> None:
    config_dir.mkdir(exist_ok=True)
    (config_dir / "settings.json").write_text(json.dumps({"hooks": hooks}, indent=2))


def test_invalid_json_is_an_error(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text("{not valid json")

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert "not valid JSON" in errors[0].message
    assert errors[0].source == "config/settings.json"


def test_non_utf8_settings_json_does_not_crash_and_warns(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Otherwise-valid JSON with a Windows-1252 byte (not valid UTF-8) in a
    # string value - a common artifact of a copy-paste from Word/Docs.
    (config_dir / "settings.json").write_bytes(b'{"hooks": {}, "note": "caf\xe9"}')

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    assert any("not valid UTF-8" in i.message for i in issues)
    assert not any("not valid JSON" in i.message for i in issues)


def test_missing_settings_json_is_not_reported(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("Some rules.\n")

    issues = check_structure(config_dir=config_dir, repo_dir=repo_dir)

    assert not any("settings.json" in i.source and i.severity == "error" for i in issues)


def test_hook_referencing_missing_script_is_an_error(tmp_path):
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "python3 hooks/missing.py"}],
                }
            ]
        },
    )

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert "hooks/missing.py" in errors[0].message
    assert "PreToolUse" in errors[0].message


def test_hook_command_expands_claude_project_dir_to_repo_dir(tmp_path):
    """Real Claude Code settings.json hooks commonly use $CLAUDE_PROJECT_DIR
    for portability - it must resolve against the repo being checked, not be
    treated as a literal, always-missing path segment."""
    config_dir = tmp_path / "config"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    hooks_dir = repo_dir / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "check.sh").write_text("#!/bin/sh\n")
    _write_settings(
        config_dir,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/check.sh",
                        }
                    ],
                }
            ]
        },
    )

    issues = check_structure(config_dir=config_dir, repo_dir=repo_dir)

    assert not any(i.severity == "error" for i in issues)


def test_hook_command_with_unresolvable_env_var_degrades_to_warn(tmp_path):
    """A env var other than $CLAUDE_PROJECT_DIR can't be resolved without a
    real shell environment; the check can't tell if it's genuinely missing,
    so it must not claim a hard error."""
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "$SOME_OTHER_VAR/hooks/check.sh"}],
                }
            ]
        },
    )

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    assert not any(i.severity == "error" for i in issues)
    assert any(i.severity == "warn" and "check.sh" in i.message for i in issues)


def test_hook_referencing_existing_script_has_no_error(tmp_path):
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "python3 hooks/present.py"}],
                }
            ]
        },
    )
    (config_dir / "hooks").mkdir()
    (config_dir / "hooks" / "present.py").write_text("# ok")
    (config_dir / "CLAUDE.md").write_text("Rules go here.\n")

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    assert issues == []


def test_hook_command_null_does_not_crash(tmp_path):
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": None}]}]},
    )

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    # A present-but-null command is malformed settings.json, not an absent
    # one - it must warn like the non-string (42) case below, not silently
    # get coerced into an empty command with no signal at all.
    assert not any(i.severity == "error" for i in issues)
    assert any("hook command is not a string" in i.message for i in issues)


def test_hook_command_non_string_does_not_crash(tmp_path):
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": 42}]}]},
    )

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    assert not any(i.severity == "error" for i in issues)
    assert any("hook command is not a string" in i.message for i in issues)


def test_hook_command_with_no_path_token_is_not_flagged(tmp_path):
    config_dir = tmp_path / "config"
    _write_settings(
        config_dir,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "ruff check ."}],
                }
            ]
        },
    )
    (config_dir / "CLAUDE.md").write_text("Rules go here.\n")

    issues = check_structure(config_dir=config_dir, repo_dir=None)

    assert issues == []


def test_missing_claude_md_warns_vanilla_harness(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert issues == [
        StructuralIssue(
            severity="warn",
            message="vanilla harness, nothing to grade statically",
            source="repo/CLAUDE.md",
        )
    ]


def test_empty_claude_md_warns_vanilla_harness(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("   \n\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert any(i.message == "vanilla harness, nothing to grade statically" for i in issues)


def test_non_utf8_claude_md_does_not_crash_and_warns(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_bytes(b"# Rules\n\nCaf\xe9 is not ASCII.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert any("not valid UTF-8" in i.message for i in issues)
    # A decode error must not also masquerade as "no CLAUDE.md" - the file
    # has real content once decoded with replacement characters.
    assert not any(i.message == "vanilla harness, nothing to grade statically" for i in issues)


def test_nonempty_claude_md_does_not_warn_vanilla(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("# Rules\n\nDo good work.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert not any(i.message == "vanilla harness, nothing to grade statically" for i in issues)


def test_neither_dir_given_warns_vanilla(tmp_path):
    issues = check_structure(config_dir=None, repo_dir=None)

    assert len(issues) == 1
    assert issues[0].message == "vanilla harness, nothing to grade statically"


def test_npm_test_documented_without_package_json_warns(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("Run `npm test` before committing.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert any("npm test" in i.message and i.severity == "warn" for i in issues)


def test_npm_test_documented_with_package_json_does_not_warn(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("Run `npm test` before committing.\n")
    (repo_dir / "package.json").write_text("{}")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert not any("npm test" in i.message for i in issues)


def test_pytest_documented_without_markers_warns(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("Run pytest before committing.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert any("pytest" in i.message and i.severity == "warn" for i in issues)


def test_pytest_documented_with_pyproject_does_not_warn(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("Run pytest before committing.\n")
    (repo_dir / "pyproject.toml").write_text("[project]\nname = 'x'\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert not any("pytest" in i.message for i in issues)


def test_backtick_referenced_missing_file_warns(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "CLAUDE.md").write_text("See `scripts/does_not_exist.py` for details.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert any("scripts/does_not_exist.py" in i.message and i.severity == "warn" for i in issues)


def test_backtick_referenced_existing_file_does_not_warn(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "scripts").mkdir()
    (repo_dir / "scripts" / "present.py").write_text("# ok")
    (repo_dir / "CLAUDE.md").write_text("See `scripts/present.py` for details.\n")

    issues = check_structure(config_dir=None, repo_dir=repo_dir)

    assert issues == []


def test_repo_claude_md_is_preferred_over_config_claude_md(tmp_path):
    config_dir = tmp_path / "config"
    repo_dir = tmp_path / "repo"
    config_dir.mkdir()
    repo_dir.mkdir()
    (config_dir / "CLAUDE.md").write_text("Config rules.\n")
    (repo_dir / "CLAUDE.md").write_text("See `scripts/missing.py` for details.\n")

    issues = check_structure(config_dir=config_dir, repo_dir=repo_dir)

    assert len(issues) == 1
    assert issues[0].source == "repo/CLAUDE.md"


def test_config_claude_md_used_when_repo_claude_md_missing(tmp_path):
    config_dir = tmp_path / "config"
    repo_dir = tmp_path / "repo"
    config_dir.mkdir()
    repo_dir.mkdir()
    (config_dir / "CLAUDE.md").write_text("See `scripts/missing.py` for details.\n")

    issues = check_structure(config_dir=config_dir, repo_dir=repo_dir)

    assert len(issues) == 1
    assert issues[0].source == "config/CLAUDE.md"


class TestBasenameReferences:
    """A bare backticked basename cannot be resolved to one location; never warn on it."""

    def test_bare_basename_reference_does_not_warn(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "CLAUDE.md").write_text("Release helpers: `publish.sh` and `ab.py`.\n")
        issues = check_structure(None, repo)
        assert not [i for i in issues if "missing file" in i.message]

    def test_slashed_missing_path_still_warns(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "CLAUDE.md").write_text("See `scripts/nonexistent_helper.py` for details.\n")
        issues = check_structure(None, repo)
        assert [i for i in issues if "scripts/nonexistent_helper.py" in i.message]
