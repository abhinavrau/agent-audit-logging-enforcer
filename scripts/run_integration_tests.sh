#!/usr/bin/env bash
# ==============================================================================
# Runner for Agent Audit Logging End-to-End Integration Test Suite
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/terraform/main.tf" ]]; then
  ROOT_DIR="${SCRIPT_DIR}"
else
  ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

# Locate service account key if not already set
if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  for candidate in "${ROOT_DIR}"/*.json "${ROOT_DIR}/.."/*sa-key*.json "${ROOT_DIR}/.."/*credentials*.json; do
    if [[ -f "${candidate}" ]]; then
      export GOOGLE_APPLICATION_CREDENTIALS="${candidate}"
      break
    fi
  done
fi

# Locate pytest in .venv or system
VENV_PYTEST="${ROOT_DIR}/.venv/bin/pytest"
if [[ ! -x "${VENV_PYTEST}" ]]; then
  VENV_PYTEST="$(command -v pytest || echo "pytest")"
fi

DO_DEPLOY=false
DO_DEPLOY_AGENT=false
PYTEST_ARGS=()

show_help() {
  cat << 'HELP'
Usage: ./run_integration_tests.sh [OPTIONS] [PYTEST_OPTIONS]

Runs the end-to-end integration test suite against Google Cloud.
Validates Eventarc triggers and automated remediation on Gemini Enterprise agents.

Options:
  --deploy           Run 'terraform apply' to deploy/refresh remediation function and Eventarc triggers
  --deploy-agent     Deploy or update the Hello World ADK test agent to Vertex AI Agent Runtime
  --setup            Run only the test agent setup verification test (test_00_test_agent_setup.py)
  --infra            Run only the Deployment & Triggers verification test (test_01_deployment_and_triggers.py)
  --registration     Run only the Agent Registration test (test_02_ge_agent_registration_e2e.py)
  --drift            Run only the Drift & Update remediation test (test_03_ge_agent_update_e2e.py)
  --audit            Run only the Cloud Logging audit record test (test_04_cloud_logging_audit.py)
  --policy           Run only the Idempotency and Policy flags test (test_05_idempotency_and_policy_flags.py)
  -h, --help         Show this help message and exit

Examples:
  ./run_integration_tests.sh
  ./run_integration_tests.sh --deploy
  ./run_integration_tests.sh --deploy-agent
  ./run_integration_tests.sh --registration
  ./run_integration_tests.sh -k "test_agent_registration"
HELP
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy)
      DO_DEPLOY=true
      shift
      ;;
    --deploy-agent)
      DO_DEPLOY_AGENT=true
      shift
      ;;
    --setup)
      PYTEST_ARGS+=("tests/integration/test_00_test_agent_setup.py")
      shift
      ;;
    --infra)
      PYTEST_ARGS+=("tests/integration/test_01_deployment_and_triggers.py")
      shift
      ;;
    --registration)
      PYTEST_ARGS+=("tests/integration/test_02_ge_agent_registration_e2e.py")
      shift
      ;;
    --drift)
      PYTEST_ARGS+=("tests/integration/test_03_ge_agent_update_e2e.py")
      shift
      ;;
    --audit)
      PYTEST_ARGS+=("tests/integration/test_04_cloud_logging_audit.py")
      shift
      ;;
    --policy)
      PYTEST_ARGS+=("tests/integration/test_05_idempotency_and_policy_flags.py")
      shift
      ;;
    -h|--help)
      show_help
      ;;
    *)
      PYTEST_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  PYTEST_ARGS=("tests/integration/")
fi

if [[ "${DO_DEPLOY_AGENT}" == true ]]; then
  echo "=================================================================="
  echo "Deploying Hello World ADK test agent to Vertex AI Agent Runtime..."
  echo "=================================================================="
  "${ROOT_DIR}/scripts/deploy_test_agent.sh"
fi

if [[ "${DO_DEPLOY}" == true ]]; then
  echo "=================================================================="
  echo "Deploying / Refreshing Terraform infrastructure..."
  echo "=================================================================="
  (cd "${ROOT_DIR}/terraform" && terraform apply -auto-approve)
fi

echo "=================================================================="
echo "Running Agent Audit Logging End-to-End Integration Tests"
echo "Root Directory : ${ROOT_DIR}"
echo "Target         : ${PYTEST_ARGS[*]}"
echo "Credentials    : ${GOOGLE_APPLICATION_CREDENTIALS:-Default ADC}"
echo "=================================================================="

cd "${ROOT_DIR}"
"${VENV_PYTEST}" "${PYTEST_ARGS[@]}" -v -s
