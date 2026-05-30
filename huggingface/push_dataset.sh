#!/usr/bin/env bash
# Publish the AWB task dataset to the Hugging Face Hub.
#
# Prerequisites (one-time):
#   pip install "huggingface_hub[cli]"
#   hf auth login            # paste a write token from https://huggingface.co/settings/tokens
#
# Usage:
#   ./huggingface/push_dataset.sh <hf-namespace>      # e.g. ./huggingface/push_dataset.sh xmpuspus
#
# Re-running rebuilds the artifact and re-uploads (idempotent).

set -euo pipefail

NS="${1:?Pass your HF namespace, e.g. ./huggingface/push_dataset.sh xmpuspus}"
REPO="${NS}/awb-tasks"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Rebuilding dataset artifact from task YAMLs..."
python3 "${ROOT}/scripts/build_hf_dataset.py"

echo "Creating dataset repo ${REPO} (no-op if it exists)..."
hf repo create "${REPO}" --repo-type dataset -y || true

echo "Uploading..."
hf upload "${REPO}" "${ROOT}/huggingface/dataset" . --repo-type dataset

echo "Done: https://huggingface.co/datasets/${REPO}"
echo "Edit README.md usage example to point at ${REPO}."
