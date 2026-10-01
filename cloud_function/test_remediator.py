"""Unit tests for the agent audit logging remediation service."""

import unittest
from unittest.mock import MagicMock, patch

import remediator
from remediator import (
    parse_dialogflow_agent_name,
    parse_discovery_engine_agent_name,
    parse_discovery_engine_name,
    process_audit_event,
    remediate_dialogflow_agent,
    remediate_discovery_engine,
    remediate_gemini_enterprise_agent,
)


class TestRemediator(unittest.TestCase):

    def test_parse_dialogflow_agent_name(self):
        valid = "projects/my-project/locations/us-central1/agents/agent-123"
        parsed = parse_dialogflow_agent_name(valid)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed, ("my-project", "us-central1", "agent-123"))

        invalid = "invalid/path/format"
        self.assertIsNone(parse_dialogflow_agent_name(invalid))

    def test_parse_discovery_engine_name(self):
        valid = "projects/my-project/locations/global/collections/default_collection/engines/engine-abc"
        parsed = parse_discovery_engine_name(valid)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed, ("my-project", "global", "default_collection", "engine-abc"))

        invalid = "projects/my-project/engines/engine-abc"
        self.assertIsNone(parse_discovery_engine_name(invalid))

    def test_parse_discovery_engine_agent_name(self):
        valid = "projects/my-project/locations/global/collections/default_collection/engines/engine-abc/assistants/default_assistant/agents/agent-xyz"
        parsed = parse_discovery_engine_agent_name(valid)
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed,
            ("my-project", "global", "default_collection", "engine-abc", "default_assistant", "agent-xyz"),
        )

    def test_remediate_dialogflow_agent_both_flags_enabled(self):
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "projects/test-proj/locations/us-central1/agents/agent-1"
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = False

        mock_client.get_agent.return_value = mock_agent
        mock_client.update_agent.return_value = mock_agent

        result = remediate_dialogflow_agent(
            "projects/test-proj/locations/us-central1/agents/agent-1",
            agents_client=mock_client,
            enforce_telemetry=True,
            enforce_prompt=True,
        )

        self.assertEqual(result["status"], "REMEDIATED")
        self.assertIn("enable_stackdriver_logging", result["remediated_fields"])
        self.assertIn("enable_interaction_logging", result["remediated_fields"])
        mock_client.update_agent.assert_called_once()
        self.assertTrue(mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging)
        self.assertTrue(mock_agent.advanced_settings.logging_settings.enable_interaction_logging)

    def test_remediate_dialogflow_agent_only_telemetry_flag_enabled(self):
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "projects/test-proj/locations/us-central1/agents/agent-1"
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = False

        mock_client.get_agent.return_value = mock_agent
        mock_client.update_agent.return_value = mock_agent

        result = remediate_dialogflow_agent(
            "projects/test-proj/locations/us-central1/agents/agent-1",
            agents_client=mock_client,
            enforce_telemetry=True,
            enforce_prompt=False,
        )

        self.assertEqual(result["status"], "REMEDIATED")
        self.assertEqual(result["remediated_fields"], ["enable_stackdriver_logging"])
        self.assertTrue(mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging)
        self.assertFalse(mock_agent.advanced_settings.logging_settings.enable_interaction_logging)

    def test_remediate_dialogflow_agent_only_prompt_flag_enabled(self):
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "projects/test-proj/locations/us-central1/agents/agent-1"
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = False

        mock_client.get_agent.return_value = mock_agent
        mock_client.update_agent.return_value = mock_agent

        result = remediate_dialogflow_agent(
            "projects/test-proj/locations/us-central1/agents/agent-1",
            agents_client=mock_client,
            enforce_telemetry=False,
            enforce_prompt=True,
        )

        self.assertEqual(result["status"], "REMEDIATED")
        self.assertEqual(result["remediated_fields"], ["enable_interaction_logging"])
        self.assertFalse(mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging)
        self.assertTrue(mock_agent.advanced_settings.logging_settings.enable_interaction_logging)

    def test_remediate_dialogflow_agent_both_flags_disabled_skips(self):
        mock_client = MagicMock()
        result = remediate_dialogflow_agent(
            "projects/test-proj/locations/us-central1/agents/agent-1",
            agents_client=mock_client,
            enforce_telemetry=False,
            enforce_prompt=False,
        )
        self.assertEqual(result["status"], "SKIPPED_BY_POLICY")
        mock_client.get_agent.assert_not_called()

    def test_remediate_dialogflow_agent_already_compliant(self):
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "projects/test-proj/locations/us-central1/agents/agent-1"
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = True
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = True

        mock_client.get_agent.return_value = mock_agent

        result = remediate_dialogflow_agent(
            "projects/test-proj/locations/us-central1/agents/agent-1",
            agents_client=mock_client,
        )

        self.assertEqual(result["status"], "ALREADY_COMPLIANT")
        mock_client.update_agent.assert_not_called()

    def test_remediate_discovery_engine_observability_config_and_linked_agent(self):
        mock_engine_client = MagicMock()
        mock_agents_client = MagicMock()

        mock_engine = MagicMock()
        mock_engine.observability_config.observability_enabled = False
        mock_engine.observability_config.sensitive_logging_enabled = False
        mock_engine.chat_engine_metadata.dialogflow_agent = (
            "projects/test-proj/locations/global/agents/linked-agent-777"
        )
        mock_engine_client.get_engine.return_value = mock_engine

        mock_agent = MagicMock()
        mock_agent.name = "projects/test-proj/locations/global/agents/linked-agent-777"
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = False
        mock_agents_client.get_agent.return_value = mock_agent
        mock_agents_client.update_agent.return_value = mock_agent

        result = remediate_discovery_engine(
            "projects/test-proj/locations/global/collections/default_collection/engines/ge-app",
            engine_client=mock_engine_client,
            agents_client=mock_agents_client,
            enforce_telemetry=True,
            enforce_prompt=False,
        )

        self.assertEqual(result["status"], "REMEDIATED")
        self.assertEqual(
            result["engine_remediated_fields"],
            ["observability_config.observability_enabled"],
        )
        self.assertTrue(mock_engine.observability_config.observability_enabled)
        self.assertFalse(mock_engine.observability_config.sensitive_logging_enabled)
        self.assertEqual(
            result["agent_remediation_details"]["remediated_fields"],
            ["enable_stackdriver_logging"],
        )
        mock_engine_client.update_engine.assert_called_once()
        mock_agents_client.update_agent.assert_called_once()

    def test_remediate_gemini_enterprise_agent_rest_session(self):
        mock_session = MagicMock()
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "name": "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/a1/agents/ag1",
            "observabilityConfig": {
                "observabilityEnabled": False,
                "sensitiveLoggingEnabled": False,
            },
        }
        mock_session.get.return_value = get_response

        patch_response = MagicMock()
        patch_response.status_code = 200
        patch_response.json.return_value = {"status": "SUCCESS"}
        mock_session.patch.return_value = patch_response

        agent_res = "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/a1/agents/ag1"
        result = remediate_gemini_enterprise_agent(
            agent_res,
            session=mock_session,
            enforce_telemetry=True,
            enforce_prompt=True,
        )

        self.assertEqual(result["status"], "REMEDIATED")
        self.assertIn("observability_config.observability_enabled", result["remediated_fields"])
        self.assertIn("observability_config.sensitive_logging_enabled", result["remediated_fields"])
        mock_session.get.assert_called_once()
        mock_session.patch.assert_called_once()
        # Verify PATCH payload
        patch_kwargs = mock_session.patch.call_args[1]
        self.assertTrue(patch_kwargs["json"]["observabilityConfig"]["observabilityEnabled"])
        self.assertTrue(patch_kwargs["json"]["observabilityConfig"]["sensitiveLoggingEnabled"])

    def test_remediate_gemini_enterprise_agent_mock_client(self):
        mock_ge_agent_client = MagicMock()
        mock_ge_agent = MagicMock()
        mock_ge_agent.name = "projects/p/locations/global/collections/default_collection/engines/e1/assistants/a1/agents/ag1"
        mock_ge_agent.observability_config.observability_enabled = False
        mock_ge_agent.observability_config.sensitive_logging_enabled = False
        mock_ge_agent_client.get_agent.return_value = mock_ge_agent
        mock_ge_agent_client.update_agent.return_value = mock_ge_agent

        result = remediate_gemini_enterprise_agent(
            mock_ge_agent.name,
            agent_service_client=mock_ge_agent_client,
            enforce_telemetry=True,
            enforce_prompt=True,
        )
        self.assertEqual(result["status"], "REMEDIATED")
        self.assertEqual(
            result["remediated_fields"],
            [
                "observability_config.observability_enabled",
                "observability_config.sensitive_logging_enabled",
            ],
        )

    def test_process_audit_event_ge_create_agent_resolves_response_name(self):
        mock_session = MagicMock()
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "name": "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/default_assistant/agents/ag-new",
            "observabilityConfig": {},
        }
        mock_session.get.return_value = get_response
        patch_response = MagicMock()
        patch_response.status_code = 200
        mock_session.patch.return_value = patch_response

        # In Discovery Engine CreateAgent, resourceName is the parent, response.name is the agent
        event_payload = {
            "protoPayload": {
                "serviceName": "discoveryengine.googleapis.com",
                "methodName": "google.cloud.discoveryengine.v1alpha.AgentService.CreateAgent",
                "resourceName": "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/default_assistant",
                "response": {
                    "name": "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/default_assistant/agents/ag-new"
                },
            }
        }

        result = process_audit_event(event_payload, session=mock_session)
        self.assertEqual(result["status"], "REMEDIATED")
        self.assertEqual(
            result["resource"],
            "projects/my-proj/locations/global/collections/default_collection/engines/e1/assistants/default_assistant/agents/ag-new",
        )

    def test_process_audit_event_dialogflow_create(self):
        mock_agents_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.advanced_settings.logging_settings.enable_stackdriver_logging = False
        mock_agent.advanced_settings.logging_settings.enable_interaction_logging = False
        mock_agents_client.get_agent.return_value = mock_agent
        mock_agents_client.update_agent.return_value = mock_agent

        event_payload = {
            "protoPayload": {
                "serviceName": "dialogflow.googleapis.com",
                "methodName": "google.cloud.dialogflow.v3.Agents.CreateAgent",
                "resourceName": "projects/sample-p/locations/us-central1/agents/ag-123",
            }
        }

        with patch.object(remediator, "ENFORCE_DF_TELEMETRY_LOGGING", True), patch.object(
            remediator, "ENFORCE_DF_PROMPT_LOGGING", False
        ):
            result = process_audit_event(event_payload, agents_client=mock_agents_client)
            self.assertEqual(result["status"], "REMEDIATED")
            self.assertEqual(result["remediated_fields"], ["enable_stackdriver_logging"])

    def test_process_audit_event_unrelated_method_ignored(self):
        event_payload = {
            "protoPayload": {
                "serviceName": "dialogflow.googleapis.com",
                "methodName": "google.cloud.dialogflow.v3.Agents.DeleteAgent",
                "resourceName": "projects/sample-p/locations/us-central1/agents/ag-123",
            }
        }
        result = process_audit_event(event_payload)
        self.assertEqual(result["status"], "IGNORED")

    def test_process_audit_event_missing_payload(self):
        result = process_audit_event({})
        self.assertEqual(result["status"], "IGNORED")


if __name__ == "__main__":
    unittest.main()
