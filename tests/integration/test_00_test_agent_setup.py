"""Setup verification test: Verifies that the Hello World ADK test agent is present and deployed."""

import json
import os
from typing import Any, Dict
from google.auth.transport.requests import AuthorizedSession
import pytest


class TestAgentSetupVerification:
    """Verifies that the test ADK agent codebase and its provisioned Reasoning Engine exist."""

    def test_adk_agent_source_code_present(self, test_config: Dict[str, Any]):
        """Asserts that the Hello World ADK agent code is present within the codebase."""
        agent_dir = test_config["test_agent_dir"]
        assert os.path.isdir(agent_dir), f"Expected test_agent directory at {agent_dir}"

        agent_py = os.path.join(agent_dir, "app", "agent.py")
        assert os.path.isfile(agent_py), f"Expected ADK agent definition at {agent_py}"

        manifest_file = os.path.join(agent_dir, "agents-cli-manifest.yaml")
        assert os.path.isfile(manifest_file), f"Expected manifest file at {manifest_file}"

        meta_file = os.path.join(agent_dir, "deployment_metadata.json")
        meta_example = os.path.join(agent_dir, "deployment_metadata.json.example")
        assert os.path.isfile(meta_file) or os.path.isfile(meta_example), (
            f"Expected deployment metadata file or example at {agent_dir}"
        )

        target_file = meta_file if os.path.isfile(meta_file) else meta_example
        with open(target_file, "r") as f:
            metadata = json.load(f)
            assert "remote_agent_runtime_id" in metadata, "Missing remote_agent_runtime_id in metadata"
            assert metadata.get("deployment_target") == "agent_runtime"

    def test_reasoning_engine_deployed_and_ready(
        self,
        discovery_session: AuthorizedSession,
        test_config: Dict[str, Any],
    ):
        """Asserts that the Reasoning Engine is deployed and available on Vertex AI Agent Runtime."""
        reasoning_engine_id = test_config.get("reasoning_engine_id")
        if not reasoning_engine_id or reasoning_engine_id.startswith("YOUR_"):
            pytest.skip("No deployed reasoning engine configured. Run ./run_integration_tests.sh --deploy-agent or set REASONING_ENGINE_ID.")

        project_number = test_config.get("project_number")
        region = test_config.get("region", "us-central1")
        if not project_number:
            pytest.skip("Project number not resolved. Skipping live Vertex AI Reasoning Engine check.")

        url = (
            f"https://{region}-aiplatform.googleapis.com/v1beta1"
            f"/projects/{project_number}/locations/{region}/reasoningEngines/{reasoning_engine_id}"
        )

        resp = discovery_session.get(url)
        assert resp.status_code == 200, (
            f"Failed to fetch Reasoning Engine from Vertex AI Agent Runtime: HTTP {resp.status_code} - {resp.text}"
        )
        data = resp.json()
        assert reasoning_engine_id in data.get("name", "")
        assert data.get("displayName") == "hello-world-agent"
