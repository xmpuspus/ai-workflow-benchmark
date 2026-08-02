#!/bin/bash
# Release smoke test: install the just-built wheel in a fresh venv and
# exercise every CLI command end-to-end.
#
# Usage:
#   scripts/test_pypi_install.sh                # test latest wheel in dist/
#   scripts/test_pypi_install.sh dist/awb-1.1.3-py3-none-any.whl
#
# Exit code is non-zero if any command fails. Intended to run between
# `python3 -m build` and `python3 -m twine upload` to catch packaging
# bugs (missing resource files, bad entry points, broken imports on
# installed wheels that work fine in editable mode).

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEEL="${1:-$(ls -t "$REPO_ROOT/dist/"*.whl 2>/dev/null | head -1)}"

if [ -z "$WHEEL" ] || [ ! -f "$WHEEL" ]; then
    echo "ERROR: no wheel found. Run 'python3 -m build' first, or pass a wheel path."
    exit 1
fi

TEST_DIR=$(mktemp -d -t awb-smoke-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

FAIL_COUNT=0
TOTAL=0

check() {
    local name="$1"
    shift
    TOTAL=$((TOTAL + 1))
    if "$@" >/dev/null 2>&1; then
        echo "  [PASS] $name"
    else
        echo "  [FAIL] $name"
        echo "         command: $*"
        "$@" 2>&1 | tail -5 | sed 's/^/         /'
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "=== AWB release smoke test ==="
echo "Wheel:    $WHEEL"
echo "Test dir: $TEST_DIR"
echo

cd "$TEST_DIR"

echo "Creating fresh venv..."
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing wheel..."
pip install --quiet --no-cache-dir "$WHEEL"

INSTALLED_VERSION=$(awb --version 2>&1 | awk '{print $NF}')
WHEEL_VERSION=$(basename "$WHEEL" | sed -E 's/awb-([0-9.]+)-.*/\1/')
echo "Installed: awb $INSTALLED_VERSION (wheel: $WHEEL_VERSION)"

if [ "$INSTALLED_VERSION" != "$WHEEL_VERSION" ]; then
    echo "  [WARN] awb --version reports $INSTALLED_VERSION but wheel is $WHEEL_VERSION"
fi

echo
echo "--- Top-level ---"
check "awb --version" awb --version
check "awb --help" awb --help
check "awb info BF-001" awb info BF-001
check "awb tools" awb tools
check "awb validate" awb validate
check "awb quickstart" awb quickstart

echo
echo "--- Warmup ---"
check "awb warmup --help" awb warmup --help
check "awb warmup --dry-run" awb warmup --dry-run
check "awb warmup --clear" awb warmup --clear

echo
echo "--- Run (dry-run modes) ---"
check "awb run --help" awb run --help
check "awb run -t BF-001 --dry-run -y claude-code-vanilla" \
    awb run -t BF-001 --dry-run -y claude-code-vanilla
check "awb run -t BF-001 --dry-run -y codex-cli" \
    awb run -t BF-001 --dry-run -y codex-cli
check "awb run --fast-check --dry-run -y claude-code-vanilla" \
    awb run --fast-check --dry-run -y claude-code-vanilla
check "awb run --progressive --dry-run -y claude-code-vanilla" \
    awb run --progressive --dry-run -y claude-code-vanilla
check "awb run --use-uv --dry-run -y -t BF-001 claude-code-vanilla" \
    awb run --use-uv --dry-run -y -t BF-001 claude-code-vanilla

echo
echo "--- Data-dependent (requires real results dir) ---"
# Seed results dir from the repo's existing runs if available
SAMPLE_RUN_SRC="$REPO_ROOT/results/runs"
if [ -d "$SAMPLE_RUN_SRC" ]; then
    SAMPLE_RUN=$(ls -d "$SAMPLE_RUN_SRC"/*_run1 2>/dev/null | \
        while read -r d; do
            count=$(ls "$d" 2>/dev/null | wc -l)
            echo "$count $d"
        done | sort -rn | head -1 | awk '{print $2}')
    if [ -n "$SAMPLE_RUN" ]; then
        BASE=$(basename "$SAMPLE_RUN" | sed 's/_run1$//')
        mkdir -p results/runs
        cp -r "$SAMPLE_RUN" results/runs/ 2>/dev/null
        cp -r "$SAMPLE_RUN_SRC/${BASE}_run2" results/runs/ 2>/dev/null
        cp -r "$SAMPLE_RUN_SRC/${BASE}_run3" results/runs/ 2>/dev/null

        check "awb gap" awb gap "results/runs/${BASE}_run1"
        check "awb compare" awb compare \
            "results/runs/${BASE}_run1" "results/runs/${BASE}_run1"
        check "awb stability" awb stability "results/runs/${BASE}_run1"
        check "awb calibrate-difficulty" \
            awb calibrate-difficulty "results/runs/${BASE}_run1"
        check "awb calibrate-timeouts" \
            awb calibrate-timeouts "results/runs/${BASE}_run1"
        check "awb export" awb export \
            "results/runs/${BASE}_run1" -o export.json
        check "awb submit export.json" awb submit export.json
        cp export.json export2.json
        check "awb compare-submissions" \
            awb compare-submissions export.json export2.json
        check "awb leaderboard" awb leaderboard
        check "awb cost" awb cost "results/runs/${BASE}_run1"
        check "awb drift (self-baseline, exit 0)" \
            awb drift "results/runs/${BASE}_run1" --baseline "results/runs/${BASE}_run1"
    else
        echo "  [SKIP] no sample runs in $SAMPLE_RUN_SRC"
    fi
else
    echo "  [SKIP] $SAMPLE_RUN_SRC not found"
fi

echo
echo "--- Workflow subcommands ---"
check "awb workflow --help" awb workflow --help
check "awb workflow export" \
    awb workflow export claude-code-vanilla -n smoke-test -o wf.yaml
check "awb workflow validate" awb workflow validate wf.yaml
cp wf.yaml wf2.yaml
check "awb workflow diff" awb workflow diff wf.yaml wf2.yaml
mkdir -p fake-codex
printf -- "model = \"gpt-5.6-sol\"\n" > fake-codex/config.toml
printf -- "- Run tests before declaring done\n- Never edit files outside the task scope\n" \
    > fake-codex/AGENTS.md
check "awb workflow export codex-cli" \
    awb workflow export codex-cli --config-dir fake-codex -n codex-smoke -o codex.yaml
check "awb workflow validate codex-cli" awb workflow validate codex.yaml

echo
echo "--- Harness tuning (v1.5) ---"
check "awb ab --help" awb ab --help
check "awb drift --help" awb drift --help
check "awb cost --help" awb cost --help
check "awb task --help" awb task --help
check "awb trace --help" awb trace --help

echo
echo "--- Checkup (v1.6) ---"
check "awb checkup --help" awb checkup --help
mkdir -p fake-config
printf -- "- Run tests before declaring done\n- Never edit files outside the task scope\n" \
    > fake-config/CLAUDE.md
check "awb checkup --static-only" \
    awb checkup --static-only --config-dir fake-config --repo-dir .
check "awb checkup --static-only --format json" \
    awb checkup --static-only --config-dir fake-config --repo-dir . --format json
check "awb checkup codex-cli --static-only" \
    awb checkup --tool codex-cli --static-only --config-dir fake-codex --repo-dir .

echo
echo "--- Migrate ---"
mkdir -p empty-old-results
check "awb migrate-results (empty)" awb migrate-results empty-old-results

echo
echo "=== Summary ==="
echo "Passed: $((TOTAL - FAIL_COUNT))/$TOTAL"
if [ "$FAIL_COUNT" -ne 0 ]; then
    echo "FAIL: $FAIL_COUNT command(s) failed. Do NOT publish this wheel."
    exit 1
fi
echo "OK: all commands passed."
