#!/bin/bash
# Build, smoke-test, then upload to PyPI.
# The smoke test installs the wheel in a fresh venv and runs every CLI
# command — this catches packaging bugs that the editable dev install
# and pytest suite miss.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Building AWB..."
rm -rf dist/
python3 -m build

echo
echo "Running PyPI install smoke test..."
"$SCRIPT_DIR/test_pypi_install.sh"

echo
echo "Uploading to PyPI..."
python3 -m twine upload dist/*
echo "Done."
