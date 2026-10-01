"""Integration tests verifying Cloud Function Gen 2 deployment and Eventarc triggers."""

import json
import subprocess
from typing import Any, Dict
import pytest


def run_gcloud_json(args: list) -> Any:
    """Helper to run a gcloud command and parse JSON output."""
    cmd = ["gcloud"] + args + ["--format=json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


class TestDeploymentAndTriggers:
    """Validates the deployed infrastructure in Google Cloud."""

    def test_cloud_function_active(self, test_config: Dict[str, Any]):
        """Asserts that the Cloud Function Gen 2 is deployed and in ACTIVE state."""
        func_info = run_gcloud_json([
            "functions", "describe", test_config["function_name"],
            f"--region={test_config['region']}",
            f"--project={test_config['project_id']}",
        ])
        assert func_info.get("state") == "ACTIVE", f"Expected ACTIVE state, got {func_info.get('state')}"
        
        # Verify dedicated service account
        expected_sa = f"agent-logging-remediator-sa@{test_config['project_id']}.iam.gserviceaccount.com"
        actual_sa = func_info.get("serviceConfig", {}).get("serviceAccountEmail")
        assert actual_sa == expected_sa, f"Expected SA {expected_sa}, got {actual_sa}"

    def test_environment_variables_configured(self, test_config: Dict[str, Any]):
        """Asserts that all 4 policy toggle flags are configured on the Cloud Function."""
        func_info = run_gcloud_json([
            "functions", "describe", test_config["function_name"],
            f"--region={test_config['region']}",
            f"--project={test_config['project_id']}",
        ])
        env_vars = func_info.get("serviceConfig", {}).get("environmentVariables", {})

        expected_flags = [
            "ENFORCE_GE_TELEMETRY_LOGGING",
            "ENFORCE_GE_PROMPT_LOGGING",
            "ENFORCE_DF_TELEMETRY_LOGGING",
            "ENFORCE_DF_PROMPT_LOGGING",
        ]
        for flag in expected_flags:
            assert flag in env_vars, f"Missing required env var {flag} in Cloud Function config"
            assert env_vars[flag].lower() == "true", f"Expected {flag}=true, got {env_vars[flag]}"

    def test_discovery_engine_eventarc_triggers(self, test_config: Dict[str, Any]):
        """Asserts that Discovery Engine Eventarc triggers exist in global location."""
        triggers = run_gcloud_json([
            "eventarc", "triggers", "list",
            "--location=global",
            f"--project={test_config['project_id']}",
        ])
        trigger_names = [t.get("name", "").split("/")[-1] for t in triggers]

        required_ge_triggers = [
            f"{test_config['function_name']}-ge-create",
            f"{test_config['function_name']}-ge-agent-create-v1alpha",
            f"{test_config['function_name']}-ge-agent-create-v1",
            f"{test_config['function_name']}-ge-agent-create-v1main",
            f"{test_config['function_name']}-ge-agent-update-v1alpha",
            f"{test_config['function_name']}-ge-agent-update-v1",
            f"{test_config['function_name']}-ge-agent-update-v1main",
        ]

        for req in required_ge_triggers:
            assert req in trigger_names, f"Expected Eventarc trigger '{req}' not found in global triggers: {trigger_names}"

    def test_dialogflow_eventarc_triggers(self, test_config: Dict[str, Any]):
        """Asserts that Dialogflow Eventarc triggers exist in us-central1 location."""
        triggers = run_gcloud_json([
            "eventarc", "triggers", "list",
            f"--location={test_config['region']}",
            f"--project={test_config['project_id']}",
        ])
        trigger_names = [t.get("name", "").split("/")[-1] for t in triggers]
        df_trigger = f"{test_config['function_name']}-df-create"
        assert df_trigger in trigger_names, f"Expected Eventarc trigger '{df_trigger}' in regional triggers"

    def test_terraform_outputs_match_deployment(self, test_config: Dict[str, Any], terraform_outputs: Dict[str, Any]):
        """Asserts that Terraform outputs correctly reflect deployed Cloud Function details."""
        if not terraform_outputs:
            pytest.skip("Terraform outputs not available in environment.")

        assert terraform_outputs.get("cloud_function_name") == test_config["function_name"]
        assert "uri" in terraform_outputs.get("cloud_function_uri", "") or "run.app" in terraform_outputs.get("cloud_function_uri", "")
        assert test_config["project_id"] in terraform_outputs.get("service_account_email", "")
