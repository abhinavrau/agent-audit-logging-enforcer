#!/usr/bin/env bash
# ==============================================================================
# Script to run unit tests locally
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
VENV_DIR="${ROOT_DIR}/.venv"

if [[ -f "${VENV_DIR}/bin/pytest" ]]; then
  echo "Running unit tests using venv pytest..."
  cd "${ROOT_DIR}/cloud_function"
  "${VENV_DIR}/bin/pytest" -v test_remediator.py
elif [[ -f "${VENV_DIR}/bin/python3" ]]; then
  echo "Running unit tests using venv unittest..."
  cd "${ROOT_DIR}/cloud_function"
  "${VENV_DIR}/bin/python3" -m unittest test_remediator.py
else
  echo "Running unit tests using system python..."
  cd "${ROOT_DIR}/cloud_function"
  python3 -m unittest test_remediator.py
fi
