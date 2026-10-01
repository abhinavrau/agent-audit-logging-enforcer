"""End-to-end integration test: Updating an existing Agent triggers Eventarc drift remediation."""

import logging
import time
from typing import Any, Dict
import pytest
from tests.integration.conftest import GeminiEnterpriseTestClient

logger = logging.getLogger(__name__)


class TestGeminiEnterpriseAgentUpdateE2E:
    """Verifies that non-compliant updates to an existing agent are automatically remediated by Eventarc."""

    def test_agent_update_drift_triggers_eventarc_remediation(
        self,
        ge_client: GeminiEnterpriseTestClient,
        test_config: Dict[str, Any],
    ):
        """Disables logging on an existing agent and asserts Eventarc triggers auto-remediation."""
        agent_name = test_config.get("existing_agent_name")
        if not agent_name:
            pytest.skip("No existing GE agent found for drift test. (Covered by registration test).")

        logger.info("Testing drift remediation on agent: %s", agent_name)

        # 1. Fetch current agent to ensure it exists
        current_agent = ge_client.get_agent(agent_name)
        assert current_agent, f"Could not find existing agent {agent_name}"

        # 2. Disable observabilityConfig (simulating policy drift or unauthorized modification)
        logger.info("Disabling observabilityConfig on agent...")
        ge_client.patch_observability_config(
            agent_name=agent_name,
            observability_enabled=False,
            sensitive_logging_enabled=False,
        )

        # 3. Poll for Eventarc + Cloud Function remediation
        logger.info("Waiting for Eventarc UpdateAgent trigger and Cloud Function remediation...")
        remediated_agent = ge_client.poll_for_remediation(
            agent_name=agent_name,
            timeout_seconds=45,
            poll_interval=3,
            expected_telemetry=True,
            expected_prompt=True,
        )

        # 4. Assert telemetry and sensitive prompt logging were restored
        final_obs = remediated_agent.get("observabilityConfig") or {}
        logger.info("Agent successfully remediated to: %s", final_obs)
        assert final_obs.get("observabilityEnabled") is True
        assert final_obs.get("sensitiveLoggingEnabled") is True
