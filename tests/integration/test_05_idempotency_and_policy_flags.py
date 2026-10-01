"""Integration tests verifying idempotency and policy flag behavior."""

import logging
import sys
from typing import Any, Dict
import pytest

# Add cloud_function to sys.path to test remediator logic directly with live sessions
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../cloud_function")))
import remediator
from tests.integration.conftest import GeminiEnterpriseTestClient

logger = logging.getLogger(__name__)


class TestIdempotencyAndPolicyFlags:
    """Verifies idempotency and independent flag control on live resources."""

    def test_live_agent_already_compliant_is_no_op(
        self,
        discovery_session: Any,
        test_config: Dict[str, Any],
    ):
        """Remediating an already-compliant agent should return ALREADY_COMPLIANT with no modifications."""
        agent_name = test_config["existing_agent_name"]

        # Run direct remediator call against live agent
        result = remediator.remediate_gemini_enterprise_agent(
            resource_name=agent_name,
            session=discovery_session,
            enforce_telemetry=True,
            enforce_prompt=True,
        )

        assert result["status"] == "ALREADY_COMPLIANT"
        assert result.get("observability_enabled") is True
        assert result.get("sensitive_logging_enabled") is True

    def test_skipped_by_policy_when_both_flags_false(
        self,
        discovery_session: Any,
        test_config: Dict[str, Any],
    ):
        """When both GE policy flags are False, execution is skipped without API call."""
        agent_name = test_config["existing_agent_name"]
        result = remediator.remediate_gemini_enterprise_agent(
            resource_name=agent_name,
            session=discovery_session,
            enforce_telemetry=False,
            enforce_prompt=False,
        )
        assert result["status"] == "SKIPPED_BY_POLICY"
        assert result["enforce_ge_telemetry"] is False
        assert result["enforce_ge_prompt"] is False

    def test_policy_flag_matrix_isolation(self):
        """Verifies the four independent flags: 2 for Gemini Enterprise and 2 for Dialogflow."""
        # 1. Dialogflow flag isolation
        from unittest.mock import MagicMock
        mock_df = MagicMock()
        mock_df_agent = MagicMock()
        mock_df_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_df_agent.advanced_settings.logging_settings.enable_interaction_logging = False
        mock_df.get_agent.return_value = mock_df_agent
        mock_df.update_agent.return_value = mock_df_agent

        # Telemetry only
        res_tel = remediator.remediate_dialogflow_agent(
            "projects/test-p/locations/us-central1/agents/a1",
            agents_client=mock_df,
            enforce_telemetry=True,
            enforce_prompt=False,
        )
        assert res_tel["status"] == "REMEDIATED"
        assert res_tel["remediated_fields"] == ["enable_stackdriver_logging"]

        # Prompt only
        mock_df_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_df_agent.advanced_settings.logging_settings.enable_interaction_logging = False
        res_prompt = remediator.remediate_dialogflow_agent(
            "projects/test-p/locations/us-central1/agents/a1",
            agents_client=mock_df,
            enforce_telemetry=False,
            enforce_prompt=True,
        )
        assert res_prompt["status"] == "REMEDIATED"
        assert res_prompt["remediated_fields"] == ["enable_interaction_logging"]

        # 2. Gemini Enterprise flag isolation
        mock_ge = MagicMock()
        mock_ge_agent = MagicMock()
        mock_ge_agent.observability_config.observability_enabled = False
        mock_ge_agent.observability_config.sensitive_logging_enabled = False
        mock_ge.get_agent.return_value = mock_ge_agent
        mock_ge.update_agent.return_value = mock_ge_agent

        # Telemetry only
        res_ge_tel = remediator.remediate_gemini_enterprise_agent(
            "projects/p/locations/global/collections/c/engines/e/assistants/a/agents/ag1",
            agent_service_client=mock_ge,
            enforce_telemetry=True,
            enforce_prompt=False,
        )
        assert res_ge_tel["status"] == "REMEDIATED"
        assert res_ge_tel["remediated_fields"] == ["observability_config.observability_enabled"]

        # Prompt only
        mock_ge_agent.observability_config.observability_enabled = False
        mock_ge_agent.observability_config.sensitive_logging_enabled = False
        res_ge_prompt = remediator.remediate_gemini_enterprise_agent(
            "projects/p/locations/global/collections/c/engines/e/assistants/a/agents/ag1",
            agent_service_client=mock_ge,
            enforce_telemetry=False,
            enforce_prompt=True,
        )
        assert res_ge_prompt["status"] == "REMEDIATED"
        assert res_ge_prompt["remediated_fields"] == ["observability_config.sensitive_logging_enabled"]
