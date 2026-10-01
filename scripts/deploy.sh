#!/usr/bin/env bash
# ==============================================================================
# Script to deploy the Agent Audit Logging Remediation Function via gcloud CLI
# ==============================================================================

set -euo pipefail

# Configuration
PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="${2:-us-central1}"
FUNCTION_NAME="agent-audit-logging-remediator"
SERVICE_ACCOUNT_NAME="agent-logging-remediator-sa"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 4 Independent Toggle Flags (override via env vars before running deploy.sh)
ENFORCE_GE_TELEMETRY_LOGGING="${ENFORCE_GE_TELEMETRY_LOGGING:-true}"
ENFORCE_GE_PROMPT_LOGGING="${ENFORCE_GE_PROMPT_LOGGING:-true}"
ENFORCE_DF_TELEMETRY_LOGGING="${ENFORCE_DF_TELEMETRY_LOGGING:-true}"
ENFORCE_DF_PROMPT_LOGGING="${ENFORCE_DF_PROMPT_LOGGING:-true}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: Project ID is required. Pass as arg or set in gcloud config."
  echo "Usage: ./deploy.sh [PROJECT_ID] [REGION]"
  exit 1
fi

echo "=================================================================="
echo "Deploying Agent Audit Logging Enforcer to Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Flags:"
echo "  ENFORCE_GE_TELEMETRY_LOGGING=${ENFORCE_GE_TELEMETRY_LOGGING}"
echo "  ENFORCE_GE_PROMPT_LOGGING=${ENFORCE_GE_PROMPT_LOGGING}"
echo "  ENFORCE_DF_TELEMETRY_LOGGING=${ENFORCE_DF_TELEMETRY_LOGGING}"
echo "  ENFORCE_DF_PROMPT_LOGGING=${ENFORCE_DF_PROMPT_LOGGING}"
echo "=================================================================="

# 1. Enable Required Services
echo "[1/4] Enabling required Google Cloud APIs..."
gcloud services enable \
  cloudfunctions.googleapis.com \
  run.googleapis.com \
  eventarc.googleapis.com \
  dialogflow.googleapis.com \
  discoveryengine.googleapis.com \
  logging.googleapis.com \
  cloudbuild.googleapis.com \
  --project="${PROJECT_ID}"

# 2. Create Service Account if not already existing
echo "[2/4] Configuring dedicated Service Account..."
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
    --display-name="Agent Audit Logging Remediation SA" \
    --project="${PROJECT_ID}"
  echo "Created service account: ${SERVICE_ACCOUNT_EMAIL}"
else
  echo "Service account ${SERVICE_ACCOUNT_EMAIL} already exists."
fi

# Assign least-privilege IAM roles
ROLES=(
  "roles/dialogflow.admin"
  "roles/discoveryengine.editor"
  "roles/logging.logWriter"
  "roles/eventarc.eventReceiver"
  "roles/run.invoker"
)

for role in "${ROLES[@]}"; do
  echo "Granting ${role} to ${SERVICE_ACCOUNT_EMAIL}..."
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="${role}" \
    --condition=None --quiet >/dev/null
done

# Grant Eventarc service agent permission to publish
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com" \
  --role="roles/eventarc.serviceAgent" \
  --condition=None --quiet >/dev/null || true

# 3. Deploy Cloud Function (Gen 2)
echo "[3/4] Deploying Cloud Function (Generation 2)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/../cloud_function"

gcloud functions deploy "${FUNCTION_NAME}" \
  --gen2 \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --runtime="python311" \
  --source="${SOURCE_DIR}" \
  --entry-point="process_audit_log" \
  --trigger-event-filters="type=google.cloud.audit.log.v1.written" \
  --trigger-event-filters="serviceName=dialogflow.googleapis.com" \
  --trigger-event-filters="methodName=google.cloud.dialogflow.v3.Agents.CreateAgent" \
  --service-account="${SERVICE_ACCOUNT_EMAIL}" \
  --set-env-vars="ENFORCE_GE_TELEMETRY_LOGGING=${ENFORCE_GE_TELEMETRY_LOGGING},ENFORCE_GE_PROMPT_LOGGING=${ENFORCE_GE_PROMPT_LOGGING},ENFORCE_DF_TELEMETRY_LOGGING=${ENFORCE_DF_TELEMETRY_LOGGING},ENFORCE_DF_PROMPT_LOGGING=${ENFORCE_DF_PROMPT_LOGGING}" \
  --ingress-settings="internal-only" \
  --quiet

# Helper for creating or updating Eventarc triggers
create_trigger_if_missing() {
  local name="$1"
  local location="$2"
  local service="$3"
  local method="$4"

  if ! gcloud eventarc triggers describe "${name}" --location="${location}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating trigger: ${name} (location: ${location}, method: ${method})..."
    gcloud eventarc triggers create "${name}" \
      --location="${location}" \
      --project="${PROJECT_ID}" \
      --destination-run-service="${FUNCTION_NAME}" \
      --destination-run-region="${REGION}" \
      --event-filters="type=google.cloud.audit.log.v1.written" \
      --event-filters="serviceName=${service}" \
      --event-filters="methodName=${method}" \
      --service-account="${SERVICE_ACCOUNT_EMAIL}" \
      --quiet
  else
    echo "Trigger ${name} already exists."
  fi
}

# 4. Create Discovery Engine triggers (in location 'global')
echo "[4/4] Configuring Discovery Engine Eventarc triggers..."
create_trigger_if_missing "${FUNCTION_NAME}-ge-create" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1.EngineService.CreateEngine"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-create-v1alpha" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1alpha.AgentService.CreateAgent"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-create-v1" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1.AgentService.CreateAgent"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-update-v1alpha" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1alpha.AgentService.UpdateAgent"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-create-v1main" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1main.AgentService.CreateAgent"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-update-v1main" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1main.AgentService.UpdateAgent"
create_trigger_if_missing "${FUNCTION_NAME}-ge-agent-update-v1" "global" "discoveryengine.googleapis.com" "google.cloud.discoveryengine.v1.AgentService.UpdateAgent"

echo "=================================================================="
echo "Deployment Complete! Agent logging enforcement is active."
echo "=================================================================="
