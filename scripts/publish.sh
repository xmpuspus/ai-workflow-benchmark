#!/bin/bash
set -e
echo "Building AWB..."
python3 -m build
echo "Uploading to PyPI..."
python3 -m twine upload dist/*
echo "Done."
