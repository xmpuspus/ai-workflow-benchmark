"""Guard tests against storefront/packaging drift.

The v1.3.0 audit found the README still led with v1.2.0, pinned
`pip install awb==1.2.0`, and referenced a baseline file that no longer
existed, while runtime deps used compatibility ranges instead of the exact
pins a reproducibility benchmark needs. These invariants keep all three from
silently going stale across releases.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from awb import __version__

_ROOT = Path(__file__).parent.parent


def test_runtime_dependencies_are_exact_pinned():
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert deps, "expected runtime dependencies"
    for spec in deps:
        assert "==" in spec and not any(
            op in spec for op in (">=", "<=", "~=", "^", ">", "<")
        ), f"runtime dep not exact-pinned (reproducibility): {spec!r}"


def test_readme_whats_new_matches_current_version():
    readme = (_ROOT / "README.md").read_text()
    assert f"What's New in v{__version__}" in readme, (
        f"README 'What's New' heading is stale; expected v{__version__}"
    )


def test_readme_baseline_references_exist():
    readme = (_ROOT / "README.md").read_text()
    refs = set(re.findall(r"results/baselines/[\w.\-]+\.json", readme))
    assert refs, "expected at least one baseline reference in README"
    for ref in refs:
        assert (_ROOT / ref).exists(), f"README references missing baseline: {ref}"


def test_readme_install_pin_matches_version():
    readme = (_ROOT / "README.md").read_text()
    pins = set(re.findall(r"pip install awb==([\d.]+)", readme))
    assert pins, "expected a pinned install example in README"
    assert pins == {__version__}, f"README pins {pins}, expected {{{__version__}}}"
