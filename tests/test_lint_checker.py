"""Tests for lint checker."""

import pytest

from awb.verification.lint_checker import _count_lines, count_lint_issues


class TestCountLines:
    def test_standard_ruff_output(self):
        output = "src/foo.py:10:5: E501 line too long\nsrc/foo.py:20:1: F401 unused import"
        assert _count_lines(output) == 2

    def test_eslint_style_output(self):
        output = "src/app.js:5:3: error no-unused-vars\nsrc/app.js:12:1: warning no-console"
        assert _count_lines(output) == 2

    def test_empty_output_returns_zero(self):
        assert _count_lines("") == 0

    def test_output_with_no_matches_returns_zero(self):
        # Lines without "file:lineno" pattern don't match
        output = "All checks passed!\nNo issues found."
        assert _count_lines(output) == 0

    def test_single_match(self):
        output = "foo.py:1: E999 syntax error"
        assert _count_lines(output) == 1

    def test_ignores_lines_without_line_number(self):
        output = "foo.py:10: E501 error\nsome summary line without colon-number"
        assert _count_lines(output) == 1


class TestCountLintIssues:
    @pytest.mark.asyncio
    async def test_empty_commands_returns_zero(self, tmp_workspace):
        total = await count_lint_issues([], tmp_workspace)
        assert total == 0

    @pytest.mark.asyncio
    async def test_command_with_no_output_counts_zero(self, tmp_workspace):
        # `true` exits 0 and produces no output
        total = await count_lint_issues(["true"], tmp_workspace)
        assert total == 0

    @pytest.mark.asyncio
    async def test_command_producing_matching_output(self, tmp_workspace):
        # echo a ruff-style line so the regex matches
        cmd = "echo 'foo.py:1:1: E501 line too long'"
        total = await count_lint_issues([cmd], tmp_workspace)
        assert total == 1

    @pytest.mark.asyncio
    async def test_multiple_commands_summed(self, tmp_workspace):
        cmds = [
            "echo 'foo.py:1:1: E501 error one'",
            "echo 'bar.py:2:1: F401 error two'",
        ]
        total = await count_lint_issues(cmds, tmp_workspace)
        assert total == 2
