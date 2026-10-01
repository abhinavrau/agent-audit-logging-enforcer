#!/usr/bin/env bash
# ==============================================================================
# Deploys the Hello World ADK Test Agent to Vertex AI Agent Runtime
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_DIR="${ROOT_DIR}/test_agent"

# Locate service account key if not already set
if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  for candidate in "${ROOT_DIR}"/*.json "${ROOT_DIR}/.."/*sa-key*.json "${ROOT_DIR}/.."/*credentials*.json; do
    if [[ -f "${candidate}" ]]; then
      export GOOGLE_APPLICATION_CREDENTIALS="${candidate}"
      break
    fi
  done
fi

AGENTS_CLI="${HOME}/.local/bin/agents-cli"
if [[ ! -x "${AGENTS_CLI}" ]]; then
  AGENTS_CLI="$(command -v agents-cli || echo "agents-cli")"
fi

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo "")}}"
REGION="${2:-${GOOGLE_CLOUD_REGION:-us-central1}}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: Project ID is required. Set GOOGLE_CLOUD_PROJECT or pass as arg."
  exit 1
fi

echo "=================================================================="
echo "Deploying Hello World ADK Agent to Vertex AI Agent Runtime"
echo "Project   : ${PROJECT_ID}"
echo "Region    : ${REGION}"
echo "Agent Dir : ${AGENT_DIR}"
echo "=================================================================="

cd "${AGENT_DIR}"
"${AGENTS_CLI}" deploy agent-runtime \
  --project="${PROJECT_ID}" \
  --region="${REGION}"

echo "=================================================================="
echo "Deployment Complete! Metadata written to:"
echo "  ${AGENT_DIR}/deployment_metadata.json"
echo "=================================================================="
