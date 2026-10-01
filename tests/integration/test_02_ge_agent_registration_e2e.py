"""End-to-end integration test: Agent Registration in Gemini Enterprise App triggers Eventarc remediation."""

import logging
import time
from typing import Any, Dict

import pytest

from tests.integration.conftest import GeminiEnterpriseTestClient

logger = logging.getLogger(__name__)


class TestGeminiEnterpriseAgentRegistrationE2E:
    """Verifies that registering a new agent into Gemini Enterprise App triggers Eventarc and remediates logging."""

    def test_agent_registration_triggers_eventarc_flow(
        self,
        ge_client: GeminiEnterpriseTestClient,
        test_config: Dict[str, Any],
    ):
        """Creates a new agent in GE App with logging disabled and verifies Eventarc auto-enables logging."""
        timestamp = int(time.time())
        display_name = f"Test Registered Agent {timestamp}"
        agent_name = None

        try:
            # 1. Register agent with logging explicitly disabled
            logger.info("Registering new agent in GE App: %s", display_name)
            create_resp = ge_client.create_agent(
                display_name=display_name,
                reasoning_engine_id=test_config["reasoning_engine_id"],
                tool_description="Temporary agent created by automated integration test",
                observability_enabled=False,
                sensitive_logging_enabled=False,
            )
            agent_name = create_resp.get("name")
            assert (
                agent_name
            ), f"Failed to retrieve agent name from create response: {create_resp}"
            logger.info("Successfully registered agent: %s", agent_name)

            # Check initial state: observabilityConfig should not have both enabled
            initial_obs = create_resp.get("observabilityConfig") or {}
            logger.info("Initial observabilityConfig on registration: %s", initial_obs)
            assert not initial_obs.get(
                "observabilityEnabled", False
            ) or not initial_obs.get(
                "sensitiveLoggingEnabled", False
            ), f"Expected logging to be disabled initially, got: {initial_obs}"

            # 2. Wait for Eventarc trigger to detect Cloud Audit Log and invoke Cloud Function
            logger.info("Polling for Eventarc + Cloud Function remediation...")
            remediated_agent = ge_client.poll_for_remediation(
                agent_name=agent_name,
                timeout_seconds=45,
                poll_interval=3,
                expected_telemetry=True,
                expected_prompt=True,
            )

            # 3. Assert remediation succeeded
            final_obs = remediated_agent.get("observabilityConfig") or {}
            logger.info("Final remediated observabilityConfig: %s", final_obs)
            assert (
                final_obs.get("observabilityEnabled") is True
            ), f"Expected observabilityEnabled=True, got {final_obs}"
            assert (
                final_obs.get("sensitiveLoggingEnabled") is True
            ), f"Expected sensitiveLoggingEnabled=True, got {final_obs}"
            assert (
                remediated_agent.get("state") == "ENABLED"
            ), f"Expected agent state ENABLED, got {remediated_agent.get('state')}"

        finally:
            # Clean up the test agent
            if agent_name:
                logger.info("Cleaning up registered test agent: %s", agent_name)
                try:
                    ge_client.delete_agent(agent_name)
                    logger.info("Test agent successfully deleted.")
                except Exception as e:
                    logger.warning("Failed to delete test agent %s: %s", agent_name, e)
