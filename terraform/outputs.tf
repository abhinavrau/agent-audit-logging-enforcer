output "cloud_function_name" {
  description = "The name of the deployed Cloud Function (Gen 2)."
  value       = google_cloudfunctions2_function.remediator.name
}

output "cloud_function_uri" {
  description = "The URI of the deployed Cloud Function (Gen 2) remediation service."
  value       = google_cloudfunctions2_function.remediator.service_config[0].uri
}

output "service_account_email" {
  description = "The dedicated service account email used by the remediation function."
  value       = google_service_account.remediator_sa.email
}

output "eventarc_trigger_dialogflow" {
  description = "The Eventarc trigger ID listening for Dialogflow CX agent events."
  value       = google_eventarc_trigger.dialogflow_agent_create.id
}

output "eventarc_trigger_discoveryengine_engine_create" {
  description = "The Eventarc trigger ID listening for Discovery Engine engine events."
  value       = google_eventarc_trigger.discoveryengine_engine_create.id
}

output "eventarc_trigger_discoveryengine_agent_create_v1alpha" {
  description = "The Eventarc trigger ID listening for Discovery Engine CreateAgent (v1alpha) events."
  value       = google_eventarc_trigger.discoveryengine_agent_create_v1alpha.id
}

output "eventarc_trigger_discoveryengine_agent_create_v1" {
  description = "The Eventarc trigger ID listening for Discovery Engine CreateAgent (v1) events."
  value       = google_eventarc_trigger.discoveryengine_agent_create_v1.id
}

output "eventarc_trigger_discoveryengine_agent_update_v1alpha" {
  description = "The Eventarc trigger ID listening for Discovery Engine UpdateAgent (v1alpha) events."
  value       = google_eventarc_trigger.discoveryengine_agent_update_v1alpha.id
}

output "eventarc_trigger_discoveryengine_agent_create_v1main" {
  description = "The Eventarc trigger ID listening for Discovery Engine CreateAgent (v1main) events."
  value       = google_eventarc_trigger.discoveryengine_agent_create_v1main.id
}

output "eventarc_trigger_discoveryengine_agent_update_v1main" {
  description = "The Eventarc trigger ID listening for Discovery Engine UpdateAgent (v1main) events."
  value       = google_eventarc_trigger.discoveryengine_agent_update_v1main.id
}

output "eventarc_trigger_discoveryengine_agent_update_v1" {
  description = "The Eventarc trigger ID listening for Discovery Engine UpdateAgent (v1) events."
  value       = google_eventarc_trigger.discoveryengine_agent_update_v1.id
}
