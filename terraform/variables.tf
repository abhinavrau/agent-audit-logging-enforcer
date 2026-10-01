variable "project_id" {
  description = "The Google Cloud Project ID where the remediation function and Eventarc triggers will be deployed."
  type        = string
}

variable "region" {
  description = "The Google Cloud region for deploying the Cloud Function and Eventarc triggers (e.g. us-central1)."
  type        = string
  default     = "us-central1"
}

variable "function_name" {
  description = "The name of the Cloud Function (Gen 2) remediation service."
  type        = string
  default     = "agent-audit-logging-remediator"
}

# -----------------------------------------------------------------------------
# 4 Independent Toggle Flags (2 for Gemini Enterprise, 2 for Dialogflow CX)
# -----------------------------------------------------------------------------

variable "enforce_ge_telemetry_logging" {
  description = "Gemini Enterprise: Whether to enforce telemetry/observability logging (observability_config.observability_enabled) across all Gemini Enterprise apps and agents."
  type        = bool
  default     = true
}

variable "enforce_ge_prompt_logging" {
  description = "Gemini Enterprise: Whether to enforce sensitive prompt/response logging (observability_config.sensitive_logging_enabled) across all Gemini Enterprise apps and agents."
  type        = bool
  default     = true
}

variable "enforce_df_telemetry_logging" {
  description = "Dialogflow CX: Whether to enforce Stackdriver / Cloud telemetry logging (advanced_settings.logging_settings.enable_stackdriver_logging) across all Dialogflow CX agents."
  type        = bool
  default     = true
}

variable "enforce_df_prompt_logging" {
  description = "Dialogflow CX: Whether to enforce verbatim prompt/response interaction logging (advanced_settings.logging_settings.enable_interaction_logging) across all Dialogflow CX agents."
  type        = bool
  default     = true
}
