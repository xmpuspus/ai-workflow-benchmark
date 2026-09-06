"""Independent arithmetic oracle for the opt-in container integration check."""

import runpy
from pathlib import Path

# Baseline and repaired files can have equal sizes and sub-second timestamps.
# Read the current source instead of reusing the baseline's timestamp-based pyc.
add = runpy.run_path(str(Path.cwd() / "solution.py"))["add"]

assert add(2, 3) == 5
assert add(-8, 4) == -4
assert add(0, 0) == 0
