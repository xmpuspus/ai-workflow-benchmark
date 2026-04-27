"""Tests for the security scanner — covers missing-binary surfacing."""

from __future__ import annotations

from pathlib import Path

import pytest

from awb.verification.security_scanner import count_security_issues, run_security_scan


@pytest.mark.asyncio
async def test_missing_scanner_binary_surfaces_warning(tmp_path: Path):
    """A bandit/semgrep that isn't installed must NOT silently report clean."""
    cmd = "this-binary-does-not-exist-9999 --scan ."
    all_clean, output = await run_security_scan([cmd], tmp_path)
    assert all_clean is False, "missing scanner must NOT be reported as clean"
    assert "scanner not found" in output.lower(), (
        f"output should mention missing scanner; got: {output!r}"
    )


@pytest.mark.asyncio
async def test_no_commands_is_trivially_clean(tmp_path: Path):
    all_clean, output = await run_security_scan([], tmp_path)
    assert all_clean is True
    assert output == ""


@pytest.mark.asyncio
async def test_missing_scanner_does_not_inflate_findings_count(tmp_path: Path):
    """count_security_issues should not count missing-binary noise as findings."""
    cmd = "this-binary-does-not-exist-9999 --scan ."
    n = await count_security_issues([cmd], tmp_path)
    assert n == 0
