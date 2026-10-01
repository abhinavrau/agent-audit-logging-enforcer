"""Cloud Function entrypoint for automated agent audit logging remediation.

Subscribes to Eventarc CloudEvents emitted by Cloud Audit Logs when agents/engines
are created or updated in Vertex AI Agent Platform or Gemini Enterprise.
"""

import json
import logging
import sys
from typing import Any

from cloudevents.http import CloudEvent
import functions_framework

from remediator import process_audit_event

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("agent-audit-logging-remediator")


@functions_framework.cloud_event
def process_audit_log(cloud_event: CloudEvent) -> None:
    """Processes an incoming CloudEvent triggered by Cloud Audit Logs via Eventarc.

    Args:
        cloud_event: The CloudEvent object containing the audit log payload.
    """
    logger.info("Received CloudEvent: id=%s, type=%s, source=%s",
                cloud_event["id"], cloud_event["type"], cloud_event["source"])

    # CloudEvent data can be bytes, string, or already parsed dict
    raw_data = cloud_event.data
    if isinstance(raw_data, (bytes, bytearray)):
        try:
            event_data = json.loads(raw_data.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to decode byte payload: %s", e)
            return
    elif isinstance(raw_data, str):
        try:
            event_data = json.loads(raw_data)
        except Exception as e:
            logger.error("Failed to parse string payload as JSON: %s", e)
            return
    elif isinstance(raw_data, dict):
        event_data = raw_data
    else:
        logger.error("Unsupported data type in CloudEvent: %s", type(raw_data))
        return

    result = process_audit_event(event_data)
    logger.info("Remediation execution completed with result: %s", json.dumps(result))


# For local testing via direct HTTP invocation if needed
@functions_framework.http
def handle_http_request(request: Any) -> Any:
    """HTTP fallback endpoint allowing manual triggering and health-checks."""
    if request.method == "GET":
        return ("Agent Logging Remediation Service is Healthy", 200)

    request_json = request.get_json(silent=True)
    if not request_json:
        return ("Bad Request: JSON body required", 400)

    result = process_audit_event(request_json)
    return (json.dumps(result), 200, {"Content-Type": "application/json"})
