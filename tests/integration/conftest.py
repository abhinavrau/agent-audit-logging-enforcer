"""Pytest fixtures and configuration for Agent Audit Logging integration tests."""

import glob
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, Generator, Optional

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import logging as cloud_logging
import pytest

logger = logging.getLogger(__name__)

# Auto-detect local service account key if GOOGLE_APPLICATION_CREDENTIALS not set
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parent_dir = os.path.dirname(base_dir)
    key_candidates = (
        glob.glob(os.path.join(base_dir, "*.json"))
        + glob.glob(os.path.join(parent_dir, "*sa-key*.json"))
        + glob.glob(os.path.join(parent_dir, "*credentials*.json"))
    )
    for candidate in key_candidates:
        if os.path.isfile(candidate) and ("key" in candidate or "credentials" in candidate):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = candidate
            break


class GeminiEnterpriseTestClient:
    """Helper client for interacting with Gemini Enterprise (Discovery Engine) Agent APIs."""

    def __init__(self, session: AuthorizedSession, project_id: str, project_number: str, engine_id: str):
        self.session = session
        self.project_id = project_id
        self.project_number = project_number
        self.engine_id = engine_id
        self.headers = {"x-goog-user-project": project_id}
        self.base_url = "https://discoveryengine.googleapis.com/v1alpha"
        self.parent_assistant = (
            f"projects/{project_number}/locations/global/collections/default_collection"
            f"/engines/{engine_id}/assistants/default_assistant"
        )

    def get_agent(self, agent_name: str) -> Dict[str, Any]:
        """Fetches the GE Agent resource by full resource name."""
        url = f"{self.base_url}/{agent_name}"
        resp = self.session.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def create_agent(
        self,
        display_name: str,
        reasoning_engine_id: str,
        reasoning_engine_location: str = "us-central1",
        tool_description: str = "Integration Test Agent",
        observability_enabled: bool = False,
        sensitive_logging_enabled: bool = False,
    ) -> Dict[str, Any]:
        """Registers a new Agent in the Gemini Enterprise App."""
        url = f"{self.base_url}/{self.parent_assistant}/agents"
        body = {
            "displayName": display_name,
            "description": "Integration test created agent",
            "icon": {
                "uri": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/smart_toy/default/24px.svg"
            },
            "adkAgentDefinition": {
                "toolSettings": {"toolDescription": tool_description},
                "provisionedReasoningEngine": {
                    "reasoningEngine": (
                        f"projects/{self.project_number}/locations/{reasoning_engine_location}"
                        f"/reasoningEngines/{reasoning_engine_id}"
                    )
                },
            },
            "observabilityConfig": {
                "observabilityEnabled": observability_enabled,
                "sensitiveLoggingEnabled": sensitive_logging_enabled,
            },
        }
        resp = self.session.post(url, json=body, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def patch_observability_config(
        self,
        agent_name: str,
        observability_enabled: bool,
        sensitive_logging_enabled: bool,
    ) -> Dict[str, Any]:
        """Updates the observabilityConfig of an existing Agent."""
        url = f"{self.base_url}/{agent_name}?updateMask=observabilityConfig"
        body = {
            "observabilityConfig": {
                "observabilityEnabled": observability_enabled,
                "sensitiveLoggingEnabled": sensitive_logging_enabled,
            }
        }
        resp = self.session.patch(url, json=body, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def delete_agent(self, agent_name: str) -> None:
        """Deletes an Agent from the Gemini Enterprise App."""
        url = f"{self.base_url}/{agent_name}"
        resp = self.session.delete(url, headers=self.headers)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def poll_for_remediation(
        self,
        agent_name: str,
        timeout_seconds: int = 45,
        poll_interval: int = 3,
        expected_telemetry: bool = True,
        expected_prompt: bool = True,
    ) -> Dict[str, Any]:
        """Polls the agent until observabilityConfig matches expected compliance or timeout."""
        start_time = time.time()
        last_obs: Dict[str, Any] = {}

        while time.time() - start_time < timeout_seconds:
            agent = self.get_agent(agent_name)
            last_obs = agent.get("observabilityConfig") or {}
            telemetry_ok = (last_obs.get("observabilityEnabled") is True) if expected_telemetry else True
            prompt_ok = (last_obs.get("sensitiveLoggingEnabled") is True) if expected_prompt else True

            if telemetry_ok and prompt_ok:
                return agent
            time.sleep(poll_interval)

        elapsed = time.time() - start_time
        raise TimeoutError(
            f"Agent {agent_name} was not remediated within {elapsed:.1f}s. "
            f"Current observabilityConfig: {last_obs}"
        )


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Dynamically resolves test environment configuration from active GCP environment."""
    # 1. Project ID
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if not project_id:
        try:
            proc = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True)
            out = proc.stdout.strip().split()
            if out:
                project_id = out[-1]
        except Exception:
            pass

    if not project_id:
        raise ValueError("Project ID could not be determined. Please set GOOGLE_CLOUD_PROJECT environment variable.")

    # 2. Project Number
    project_number = os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER")
    if not project_number and project_id:
        try:
            proc = subprocess.run(
                ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
                capture_output=True,
                text=True,
            )
            project_number = proc.stdout.strip()
        except Exception:
            pass

    region = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    function_name = os.getenv("REMEDIATOR_FUNCTION_NAME", "agent-audit-logging-remediator")

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tf_dir = os.path.join(base_dir, "terraform")
    test_agent_dir = os.path.join(base_dir, "test_agent")
    agent_meta_file = os.path.join(test_agent_dir, "deployment_metadata.json")

    # 3. Reasoning Engine ID resolution
    reasoning_engine_id = os.getenv("REASONING_ENGINE_ID")
    if not reasoning_engine_id and os.path.exists(agent_meta_file):
        try:
            with open(agent_meta_file, "r") as f:
                meta = json.load(f)
                rt_id = meta.get("remote_agent_runtime_id", "")
                if rt_id and not rt_id.endswith("YOUR_REASONING_ENGINE_ID"):
                    reasoning_engine_id = rt_id.split("/")[-1]
        except Exception as e:
            logger.warning("Could not read reasoning engine ID from metadata: %s", e)

    # If still not found, auto-discover from Vertex AI Reasoning Engines
    if not reasoning_engine_id and project_number:
        try:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(creds)
            re_url = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{project_number}/locations/{region}/reasoningEngines"
            resp = session.get(re_url)
            if resp.status_code == 200:
                engines = resp.json().get("reasoningEngines", [])
                for re in engines:
                    if re.get("displayName") == "hello-world-agent":
                        reasoning_engine_id = re.get("name").split("/")[-1]
                        break
                if not reasoning_engine_id and engines:
                    reasoning_engine_id = engines[0].get("name").split("/")[-1]
        except Exception as e:
            logger.warning("Could not auto-discover reasoning engine: %s", e)

    # 4. Gemini Enterprise Engine (GE_APP_ID)
    ge_app_id = os.getenv("GE_APP_ID")
    if not ge_app_id and project_number:
        try:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(creds)
            ge_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_number}/locations/global/collections/default_collection/engines"
            resp_ge = session.get(ge_url, headers={"x-goog-user-project": project_id})
            if resp_ge.status_code == 200:
                engines = resp_ge.json().get("engines", [])
                for eng in engines:
                    name = eng.get("name", "").split("/")[-1]
                    if "data-insights" in name:
                        ge_app_id = name
                        break
                if not ge_app_id and engines:
                    ge_app_id = engines[0].get("name").split("/")[-1]
        except Exception as e:
            logger.warning("Could not auto-discover GE app ID: %s", e)

    # 5. Existing agent for drift remediation testing
    existing_agent_id = os.getenv("GE_AGENT_ID")
    existing_agent_name = None
    if existing_agent_id and ge_app_id and project_number:
        existing_agent_name = (
            f"projects/{project_number}/locations/global/collections/default_collection"
            f"/engines/{ge_app_id}/assistants/default_assistant/agents/{existing_agent_id}"
        )
    elif ge_app_id and project_number:
        try:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(creds)
            agents_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_number}/locations/global/collections/default_collection/engines/{ge_app_id}/assistants/default_assistant/agents"
            resp_ag = session.get(agents_url, headers={"x-goog-user-project": project_id})
            if resp_ag.status_code == 200:
                agents = resp_ag.json().get("agents", [])
                if agents:
                    existing_agent_name = agents[0].get("name")
        except Exception as e:
            logger.warning("Could not auto-discover existing agent: %s", e)

    return {
        "project_id": project_id,
        "project_number": project_number,
        "region": region,
        "function_name": function_name,
        "ge_app_id": ge_app_id,
        "reasoning_engine_id": reasoning_engine_id,
        "existing_agent_name": existing_agent_name,
        "terraform_dir": tf_dir,
        "test_agent_dir": test_agent_dir,
    }


@pytest.fixture(scope="session")
def terraform_outputs(test_config: Dict[str, Any]) -> Dict[str, Any]:
    """Reads Terraform outputs from the deployed environment."""
    tf_dir = test_config["terraform_dir"]
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=tf_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return {k: v["value"] for k, v in data.items()}
    except Exception as e:
        logger.warning("Could not read terraform output: %s", e)
        return {}


@pytest.fixture(scope="session")
def discovery_session() -> AuthorizedSession:
    """Authenticated AuthorizedSession for Discovery Engine API."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return AuthorizedSession(credentials)


@pytest.fixture(scope="session")
def ge_client(discovery_session: AuthorizedSession, test_config: Dict[str, Any]) -> GeminiEnterpriseTestClient:
    """Instantiated Gemini Enterprise helper client."""
    return GeminiEnterpriseTestClient(
        session=discovery_session,
        project_id=test_config["project_id"],
        project_number=test_config["project_number"],
        engine_id=test_config["ge_app_id"],
    )


@pytest.fixture(scope="session")
def logging_client(test_config: Dict[str, Any]) -> cloud_logging.Client:
    """Google Cloud Logging client."""
    return cloud_logging.Client(project=test_config["project_id"])
