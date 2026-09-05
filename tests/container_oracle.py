"""Independent arithmetic oracle for the opt-in container integration check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from solution import add  # noqa: E402

assert add(2, 3) == 5
assert add(-8, 4) == -4
assert add(0, 0) == 0
