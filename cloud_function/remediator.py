"""Core remediation logic for enforcing agent observability and prompt logging.

This module inspects agent resources (Dialogflow CX agents and Gemini Enterprise
Discovery Engine chat engines / agents) triggered by Cloud Audit Log events, and
enforces telemetry logging and prompt/response logging via 4 independent flags:
  1. ENFORCE_GE_TELEMETRY_LOGGING (Gemini Enterprise Telemetry / Observability)
  2. ENFORCE_GE_PROMPT_LOGGING    (Gemini Enterprise Sensitive Prompt/Response Logging)
  3. ENFORCE_DF_TELEMETRY_LOGGING (Dialogflow CX Cloud/Stackdriver Telemetry Logging)
  4. ENFORCE_DF_PROMPT_LOGGING    (Dialogflow CX Interaction Prompt/Response Logging)
"""

import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

import google.auth
from google.api_core import client_options
from google.auth.transport.requests import AuthorizedSession
from google.cloud import dialogflowcx_v3
from google.cloud import discoveryengine_v1
from google.protobuf import field_mask_pb2

logger = logging.getLogger(__name__)

# Resource name regex patterns for strict input validation
DIALOGFLOW_AGENT_PATTERN = re.compile(
    r"^projects/([a-zA-Z0-9_\-]+)/locations/([a-zA-Z0-9_\-]+)/agents/([a-zA-Z0-9_\-]+)$"
)
DISCOVERY_ENGINE_PATTERN = re.compile(
    r"^projects/([a-zA-Z0-9_\-]+)/locations/([a-zA-Z0-9_\-]+)/collections/([a-zA-Z0-9_\-]+)/engines/([a-zA-Z0-9_\-]+)$"
)
DISCOVERY_ENGINE_AGENT_PATTERN = re.compile(
    r"^projects/([a-zA-Z0-9_\-]+)/locations/([a-zA-Z0-9_\-]+)/collections/([a-zA-Z0-9_\-]+)/engines/([a-zA-Z0-9_\-]+)/assistants/([a-zA-Z0-9_\-]+)/agents/([a-zA-Z0-9_\-]+)$"
)

# ---------------------------------------------------------------------------
# Feature Flags (4 independent toggles: 2 for Gemini Enterprise, 2 for Dialogflow)
# ---------------------------------------------------------------------------
ENFORCE_GE_TELEMETRY_LOGGING = (
    os.getenv("ENFORCE_GE_TELEMETRY_LOGGING", "true").lower() == "true"
)
ENFORCE_GE_PROMPT_LOGGING = (
    os.getenv("ENFORCE_GE_PROMPT_LOGGING", "true").lower() == "true"
)

ENFORCE_DF_TELEMETRY_LOGGING = (
    os.getenv("ENFORCE_DF_TELEMETRY_LOGGING", "true").lower() == "true"
)
ENFORCE_DF_PROMPT_LOGGING = (
    os.getenv("ENFORCE_DF_PROMPT_LOGGING", "true").lower() == "true"
)


def parse_dialogflow_agent_name(resource_name: str) -> Optional[Tuple[str, str, str]]:
    """Validates and parses a Dialogflow CX agent resource name into (project, location, agent_id)."""
    match = DIALOGFLOW_AGENT_PATTERN.match(resource_name)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def parse_discovery_engine_name(resource_name: str) -> Optional[Tuple[str, str, str, str]]:
    """Validates and parses a Discovery Engine resource name into (project, location, collection, engine_id)."""
    match = DISCOVERY_ENGINE_PATTERN.match(resource_name)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3), match.group(4)


def parse_discovery_engine_agent_name(
    resource_name: str,
) -> Optional[Tuple[str, str, str, str, str, str]]:
    """Validates and parses a Gemini Enterprise Agent resource name."""
    match = DISCOVERY_ENGINE_AGENT_PATTERN.match(resource_name)
    if not match:
        return None
    return (
        match.group(1),
        match.group(2),
        match.group(3),
        match.group(4),
        match.group(5),
        match.group(6),
    )


def get_dialogflow_client(location: str) -> dialogflowcx_v3.AgentsClient:
    """Instantiates a regional Dialogflow CX Agents client."""
    if location.lower() == "global":
        endpoint = "dialogflow.googleapis.com"
    else:
        endpoint = f"{location}-dialogflow.googleapis.com"
    options = client_options.ClientOptions(api_endpoint=endpoint)
    return dialogflowcx_v3.AgentsClient(client_options=options)


def get_discovery_engine_client(location: str) -> discoveryengine_v1.EngineServiceClient:
    """Instantiates a regional Discovery Engine client."""
    if location.lower() == "global":
        endpoint = "discoveryengine.googleapis.com"
    else:
        endpoint = f"{location}-discoveryengine.googleapis.com"
    options = client_options.ClientOptions(api_endpoint=endpoint)
    return discoveryengine_v1.EngineServiceClient(client_options=options)


def get_discovery_engine_session() -> AuthorizedSession:
    """Returns an authenticated AuthorizedSession with cloud-platform scope."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return AuthorizedSession(credentials)


def remediate_dialogflow_agent(
    resource_name: str,
    agents_client: Optional[dialogflowcx_v3.AgentsClient] = None,
    enforce_telemetry: Optional[bool] = None,
    enforce_prompt: Optional[bool] = None,
) -> Dict[str, Any]:
    """Inspects a Dialogflow CX agent and enforces telemetry (Stackdriver) and prompt (interaction) logging.

    Args:
        resource_name: Formatted string 'projects/{project}/locations/{location}/agents/{agent_id}'.
        agents_client: Optional injected client for testing.
        enforce_telemetry: Override flag for telemetry logging (defaults to ENFORCE_DF_TELEMETRY_LOGGING).
        enforce_prompt: Override flag for prompt logging (defaults to ENFORCE_DF_PROMPT_LOGGING).

    Returns:
        Dict detailing the outcome of the inspection and remediation.
    """
    if enforce_telemetry is None:
        enforce_telemetry = ENFORCE_DF_TELEMETRY_LOGGING
    if enforce_prompt is None:
        enforce_prompt = ENFORCE_DF_PROMPT_LOGGING

    parsed = parse_dialogflow_agent_name(resource_name)
    if not parsed:
        msg = f"Invalid Dialogflow agent resource name format: '{resource_name}'"
        logger.error(msg)
        return {"status": "ERROR", "resource": resource_name, "error": msg}

    if not enforce_telemetry and not enforce_prompt:
        logger.info(
            "Both telemetry and prompt logging enforcement flags are disabled for Dialogflow agent %s. Skipping.",
            resource_name,
        )
        return {
            "status": "SKIPPED_BY_POLICY",
            "resource": resource_name,
            "enforce_telemetry": False,
            "enforce_prompt": False,
        }

    project, location, agent_id = parsed
    client = agents_client or get_dialogflow_client(location)

    logger.info("Fetching Dialogflow CX agent: %s", resource_name)
    try:
        agent = client.get_agent(name=resource_name)
    except Exception as e:
        logger.error("Failed to fetch agent %s: %s", resource_name, e)
        return {"status": "ERROR", "resource": resource_name, "error": str(e)}

    logging_settings = agent.advanced_settings.logging_settings
    stackdriver_enabled = logging_settings.enable_stackdriver_logging
    interaction_enabled = logging_settings.enable_interaction_logging

    logger.info(
        "Current logging settings for %s: enable_stackdriver_logging=%s, enable_interaction_logging=%s "
        "(policy: enforce_telemetry=%s, enforce_prompt=%s)",
        resource_name,
        stackdriver_enabled,
        interaction_enabled,
        enforce_telemetry,
        enforce_prompt,
    )

    remediation_needed = False
    remediated_fields = []

    if enforce_telemetry and not stackdriver_enabled:
        logging_settings.enable_stackdriver_logging = True
        remediation_needed = True
        remediated_fields.append("enable_stackdriver_logging")

    if enforce_prompt and not interaction_enabled:
        logging_settings.enable_interaction_logging = True
        remediation_needed = True
        remediated_fields.append("enable_interaction_logging")

    if not remediation_needed:
        logger.info("Agent %s is already compliant with logging policy. No action required.", resource_name)
        return {
            "status": "ALREADY_COMPLIANT",
            "resource": resource_name,
            "enable_stackdriver_logging": stackdriver_enabled,
            "enable_interaction_logging": interaction_enabled,
        }

    logger.warning(
        "Agent %s is NON-COMPLIANT. Remediating fields: %s",
        resource_name,
        remediated_fields,
    )

    try:
        update_mask = field_mask_pb2.FieldMask(paths=["advanced_settings.logging_settings"])
        updated_agent = client.update_agent(agent=agent, update_mask=update_mask)
        logger.info(
            "Successfully patched agent %s to enforce logging policy.",
            resource_name,
        )
        return {
            "status": "REMEDIATED",
            "resource": resource_name,
            "remediated_fields": remediated_fields,
            "updated_agent_name": updated_agent.name,
        }
    except Exception as e:
        logger.error("Failed to patch agent %s: %s", resource_name, e)
        return {"status": "ERROR", "resource": resource_name, "error": str(e)}


def remediate_discovery_engine(
    resource_name: str,
    engine_client: Optional[discoveryengine_v1.EngineServiceClient] = None,
    agents_client: Optional[dialogflowcx_v3.AgentsClient] = None,
    enforce_telemetry: Optional[bool] = None,
    enforce_prompt: Optional[bool] = None,
) -> Dict[str, Any]:
    """Inspects a Gemini Enterprise Discovery Engine and enforces GE telemetry & prompt logging.

    Enforces:
      1. Engine-level `observability_config`:
         - `observability_enabled` (when `enforce_telemetry` is True)
         - `sensitive_logging_enabled` (when `enforce_prompt` is True)
      2. Linked Dialogflow CX agent (if present in `chat_engine_metadata.dialogflow_agent`)
         using the Gemini Enterprise toggle flags (`enforce_telemetry`, `enforce_prompt`).
    """
    if enforce_telemetry is None:
        enforce_telemetry = ENFORCE_GE_TELEMETRY_LOGGING
    if enforce_prompt is None:
        enforce_prompt = ENFORCE_GE_PROMPT_LOGGING

    parsed = parse_discovery_engine_name(resource_name)
    if not parsed:
        msg = f"Invalid Discovery Engine resource name format: '{resource_name}'"
        logger.error(msg)
        return {"status": "ERROR", "resource": resource_name, "error": msg}

    if not enforce_telemetry and not enforce_prompt:
        logger.info(
            "Both GE telemetry and GE prompt logging enforcement flags are disabled for %s. Skipping.",
            resource_name,
        )
        return {
            "status": "SKIPPED_BY_POLICY",
            "resource": resource_name,
            "enforce_ge_telemetry": False,
            "enforce_ge_prompt": False,
        }

    project, location, collection, engine_id = parsed
    client = engine_client or get_discovery_engine_client(location)

    logger.info("Fetching Gemini Enterprise Engine: %s", resource_name)
    try:
        engine = client.get_engine(name=resource_name)
    except Exception as e:
        logger.error("Failed to fetch engine %s: %s", resource_name, e)
        return {"status": "ERROR", "resource": resource_name, "error": str(e)}

    engine_remediated_fields = []
    obs_config = getattr(engine, "observability_config", None)
    if obs_config is not None:
        obs_enabled = getattr(obs_config, "observability_enabled", True)
        sensitive_enabled = getattr(obs_config, "sensitive_logging_enabled", True)

        if enforce_telemetry and obs_enabled is False:
            obs_config.observability_enabled = True
            engine_remediated_fields.append("observability_config.observability_enabled")

        if enforce_prompt and sensitive_enabled is False:
            obs_config.sensitive_logging_enabled = True
            engine_remediated_fields.append("observability_config.sensitive_logging_enabled")

        if engine_remediated_fields:
            logger.warning(
                "Gemini Enterprise Engine %s is NON-COMPLIANT. Remediating fields: %s",
                resource_name,
                engine_remediated_fields,
            )
            try:
                update_mask = field_mask_pb2.FieldMask(paths=["observability_config"])
                client.update_engine(engine=engine, update_mask=update_mask)
            except Exception as e:
                logger.error("Failed to patch Gemini Enterprise engine %s: %s", resource_name, e)
                return {"status": "ERROR", "resource": resource_name, "error": str(e)}

    # For Chat Engines in Gemini Enterprise, check if a backing Dialogflow CX agent is linked
    linked_agent = getattr(getattr(engine, "chat_engine_metadata", None), "dialogflow_agent", None)
    if not isinstance(linked_agent, str) or not linked_agent:
        if engine_remediated_fields:
            return {
                "status": "REMEDIATED",
                "engine_resource": resource_name,
                "remediated_fields": engine_remediated_fields,
            }
        logger.info(
            "Engine %s is compliant or does not reference a linked Dialogflow agent.",
            resource_name,
        )
        return {
            "status": "ALREADY_COMPLIANT" if obs_config is not None else "NO_OP",
            "resource": resource_name,
            "message": "No linked Dialogflow agent found in engine metadata.",
        }

    logger.info(
        "Engine %s maps to linked Dialogflow agent: %s. Initiating remediation with GE policy flags "
        "(enforce_telemetry=%s, enforce_prompt=%s).",
        resource_name,
        linked_agent,
        enforce_telemetry,
        enforce_prompt,
    )
    agent_result = remediate_dialogflow_agent(
        linked_agent,
        agents_client=agents_client,
        enforce_telemetry=enforce_telemetry,
        enforce_prompt=enforce_prompt,
    )
    overall_status = (
        "REMEDIATED"
        if (engine_remediated_fields or agent_result.get("status") == "REMEDIATED")
        else agent_result.get("status", "ALREADY_COMPLIANT")
    )
    return {
        "status": overall_status,
        "engine_resource": resource_name,
        "engine_remediated_fields": engine_remediated_fields,
        "linked_agent_resource": linked_agent,
        "agent_remediation_details": agent_result,
    }


def remediate_gemini_enterprise_agent(
    resource_name: str,
    agent_service_client: Optional[Any] = None,
    session: Optional[Any] = None,
    enforce_telemetry: Optional[bool] = None,
    enforce_prompt: Optional[bool] = None,
) -> Dict[str, Any]:
    """Inspects and remediates a Gemini Enterprise Agent resource (`observability_config`).

    Enforces:
      - `observability_config.observability_enabled` (when `enforce_telemetry` is True)
      - `observability_config.sensitive_logging_enabled` (when `enforce_prompt` is True)
    """
    if enforce_telemetry is None:
        enforce_telemetry = ENFORCE_GE_TELEMETRY_LOGGING
    if enforce_prompt is None:
        enforce_prompt = ENFORCE_GE_PROMPT_LOGGING

    parsed = parse_discovery_engine_agent_name(resource_name)
    if not parsed:
        msg = f"Invalid Gemini Enterprise Agent resource name format: '{resource_name}'"
        logger.error(msg)
        return {"status": "ERROR", "resource": resource_name, "error": msg}

    if not enforce_telemetry and not enforce_prompt:
        logger.info(
            "Both GE telemetry and GE prompt logging enforcement flags are disabled for GE agent %s. Skipping.",
            resource_name,
        )
        return {
            "status": "SKIPPED_BY_POLICY",
            "resource": resource_name,
            "enforce_ge_telemetry": False,
            "enforce_ge_prompt": False,
        }

    # 1. Mock Client Path (unit testing)
    if agent_service_client is not None:
        try:
            ge_agent = agent_service_client.get_agent(name=resource_name)
        except Exception as e:
            logger.error("Failed to fetch Gemini Enterprise agent %s: %s", resource_name, e)
            return {"status": "ERROR", "resource": resource_name, "error": str(e)}

        obs_config = ge_agent.observability_config
        obs_enabled = obs_config.observability_enabled
        sensitive_enabled = obs_config.sensitive_logging_enabled

        remediated_fields = []
        if enforce_telemetry and not obs_enabled:
            obs_config.observability_enabled = True
            remediated_fields.append("observability_config.observability_enabled")

        if enforce_prompt and not sensitive_enabled:
            obs_config.sensitive_logging_enabled = True
            remediated_fields.append("observability_config.sensitive_logging_enabled")

        if not remediated_fields:
            return {
                "status": "ALREADY_COMPLIANT",
                "resource": resource_name,
                "observability_enabled": obs_enabled,
                "sensitive_logging_enabled": sensitive_enabled,
            }

        try:
            update_mask = field_mask_pb2.FieldMask(paths=["observability_config"])
            updated = agent_service_client.update_agent(agent=ge_agent, update_mask=update_mask)
            return {
                "status": "REMEDIATED",
                "resource": resource_name,
                "remediated_fields": remediated_fields,
                "updated_agent_name": getattr(updated, "name", resource_name),
            }
        except Exception as e:
            logger.error("Failed to patch Gemini Enterprise agent %s: %s", resource_name, e)
            return {"status": "ERROR", "resource": resource_name, "error": str(e)}

    # 2. REST API Path (live Cloud Function execution or mock session)
    project = parsed[0]
    http_session = session or get_discovery_engine_session()
    url = f"https://discoveryengine.googleapis.com/v1alpha/{resource_name}"
    headers = {"x-goog-user-project": project}

    logger.info("Fetching Gemini Enterprise agent via REST: %s", url)
    try:
        resp = http_session.get(url, headers=headers)
        if resp.status_code == 404:
            logger.info(
                "Agent %s was not found (HTTP 404); it may have been deleted immediately after creation/update. Skipping.",
                resource_name,
            )
            return {
                "status": "NOT_FOUND",
                "resource": resource_name,
                "message": "Agent not found or already deleted",
            }
        if resp.status_code != 200:
            msg = f"Failed to get agent (HTTP {resp.status_code}): {resp.text}"
            logger.error(msg)
            return {"status": "ERROR", "resource": resource_name, "error": msg}
        agent_data = resp.json()
    except Exception as e:
        logger.error("Exception fetching agent %s: %s", resource_name, e)
        return {"status": "ERROR", "resource": resource_name, "error": str(e)}

    obs_config = agent_data.get("observabilityConfig") or {}
    obs_enabled = bool(obs_config.get("observabilityEnabled", False))
    sensitive_enabled = bool(obs_config.get("sensitiveLoggingEnabled", False))

    remediated_fields = []
    new_obs = dict(obs_config)

    if enforce_telemetry and not obs_enabled:
        new_obs["observabilityEnabled"] = True
        remediated_fields.append("observability_config.observability_enabled")

    if enforce_prompt and not sensitive_enabled:
        new_obs["sensitiveLoggingEnabled"] = True
        remediated_fields.append("observability_config.sensitive_logging_enabled")

    if not remediated_fields:
        logger.info("Gemini Enterprise agent %s is already compliant.", resource_name)
        return {
            "status": "ALREADY_COMPLIANT",
            "resource": resource_name,
            "observability_enabled": obs_enabled,
            "sensitive_logging_enabled": sensitive_enabled,
        }

    logger.warning(
        "Gemini Enterprise agent %s is NON-COMPLIANT. Remediating fields: %s",
        resource_name,
        remediated_fields,
    )

    try:
        patch_url = f"{url}?updateMask=observabilityConfig"
        patch_body = {"observabilityConfig": new_obs}
        patch_resp = http_session.patch(patch_url, json=patch_body, headers=headers)
        if patch_resp.status_code != 200:
            msg = f"Failed to patch agent (HTTP {patch_resp.status_code}): {patch_resp.text}"
            logger.error(msg)
            return {"status": "ERROR", "resource": resource_name, "error": msg}

        logger.info("Successfully patched GE agent %s observabilityConfig.", resource_name)
        return {
            "status": "REMEDIATED",
            "resource": resource_name,
            "remediated_fields": remediated_fields,
            "observability_config": new_obs,
        }
    except Exception as e:
        logger.error("Exception patching GE agent %s: %s", resource_name, e)
        return {"status": "ERROR", "resource": resource_name, "error": str(e)}


def process_audit_event(
    event_data: Dict[str, Any],
    agents_client: Optional[dialogflowcx_v3.AgentsClient] = None,
    engine_client: Optional[discoveryengine_v1.EngineServiceClient] = None,
    ge_agent_client: Optional[Any] = None,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    """Processes a parsed Cloud Audit Log event payload from Eventarc.

    Args:
        event_data: Dictionary containing the protoPayload or event payload.
        agents_client: Optional mocked Dialogflow AgentsClient for unit tests.
        engine_client: Optional mocked Discovery Engine EngineServiceClient for unit tests.
        ge_agent_client: Optional mocked Discovery Engine AgentServiceClient for unit tests.
        session: Optional HTTP session for REST requests.

    Returns:
        Result summary dictionary.
    """
    proto_payload = event_data.get("protoPayload", {})
    if not proto_payload:
        logger.warning("Event payload missing 'protoPayload'. Skipping.")
        return {"status": "IGNORED", "reason": "Missing protoPayload"}

    service_name = proto_payload.get("serviceName", "")
    method_name = proto_payload.get("methodName", "")
    resource_name = proto_payload.get("resourceName", "")

    logger.info(
        "Evaluating audit event: service=%s, method=%s, resource=%s",
        service_name,
        method_name,
        resource_name,
    )

    if not resource_name:
        return {"status": "IGNORED", "reason": "No resourceName in audit log"}

    # 1. Handle Dialogflow CX Agents (uses ENFORCE_DF_TELEMETRY_LOGGING & ENFORCE_DF_PROMPT_LOGGING)
    if "dialogflow.googleapis.com" in service_name:
        if any(method in method_name for method in ["CreateAgent", "UpdateAgent"]):
            return remediate_dialogflow_agent(
                resource_name,
                agents_client=agents_client,
                enforce_telemetry=ENFORCE_DF_TELEMETRY_LOGGING,
                enforce_prompt=ENFORCE_DF_PROMPT_LOGGING,
            )
        return {"status": "IGNORED", "reason": f"Unhandled Dialogflow method: {method_name}"}

    # 2. Handle Discovery Engine / Gemini Enterprise (uses ENFORCE_GE_TELEMETRY_LOGGING & ENFORCE_GE_PROMPT_LOGGING)
    if "discoveryengine.googleapis.com" in service_name:
        if any(method in method_name for method in ["CreateEngine", "UpdateEngine"]):
            return remediate_discovery_engine(
                resource_name,
                engine_client=engine_client,
                agents_client=agents_client,
                enforce_telemetry=ENFORCE_GE_TELEMETRY_LOGGING,
                enforce_prompt=ENFORCE_GE_PROMPT_LOGGING,
            )
        if any(method in method_name for method in ["CreateAgent", "UpdateAgent"]):
            # Extract full agent resource name if resourceName is the parent assistant
            agent_resource_name = (
                proto_payload.get("response", {}).get("name")
                or proto_payload.get("request", {}).get("agent", {}).get("name")
                or resource_name
            )
            return remediate_gemini_enterprise_agent(
                agent_resource_name,
                agent_service_client=ge_agent_client,
                session=session,
                enforce_telemetry=ENFORCE_GE_TELEMETRY_LOGGING,
                enforce_prompt=ENFORCE_GE_PROMPT_LOGGING,
            )
        return {"status": "IGNORED", "reason": f"Unhandled Discovery Engine method: {method_name}"}

    return {
        "status": "IGNORED",
        "reason": f"Unsupported service: {service_name}",
    }
