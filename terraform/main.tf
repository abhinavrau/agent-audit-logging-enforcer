# ---------------------------------------------------------------------------------------------------------------------
# AGENT AUDIT LOGGING ENFORCEMENT VIA EVENTARC & CLOUD FUNCTIONS (GEN 2)
# ---------------------------------------------------------------------------------------------------------------------

data "google_project" "current" {
  project_id = var.project_id
}

# 1. Enable Required GCP APIs
locals {
  services = [
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "dialogflow.googleapis.com",
    "discoveryengine.googleapis.com",
    "logging.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
  ]
}

resource "google_project_service" "enabled_services" {
  for_each           = toset(local.services)
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# 2. Dedicated Least-Privilege Service Account for the Remediator Function
resource "google_service_account" "remediator_sa" {
  project      = var.project_id
  account_id   = "agent-logging-remediator-sa"
  display_name = "Agent Audit Logging Remediation Service Account"
  description  = "Executes automatic remediation of agent prompt and observability logging"
}

# IAM Role: Dialogflow Admin (required to inspect and patch advanced_settings.logging_settings)
resource "google_project_iam_member" "dialogflow_admin" {
  project = var.project_id
  role    = "roles/dialogflow.admin"
  member  = "serviceAccount:${google_service_account.remediator_sa.email}"
}

# IAM Role: Discovery Engine Editor (required to inspect & patch Gemini Enterprise chat engines & agents)
resource "google_project_iam_member" "discoveryengine_editor" {
  project = var.project_id
  role    = "roles/discoveryengine.editor"
  member  = "serviceAccount:${google_service_account.remediator_sa.email}"
}

# IAM Role: Logs Writer
resource "google_project_iam_member" "logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.remediator_sa.email}"
}

# IAM Role: Eventarc Event Receiver
resource "google_project_iam_member" "eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.remediator_sa.email}"
}

# Grant Eventarc Service Agent permission to publish events
resource "google_project_iam_member" "eventarc_service_agent" {
  project    = var.project_id
  role       = "roles/eventarc.serviceAgent"
  member     = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
  depends_on = [google_project_service.enabled_services]
}

# 3. Cloud Storage Bucket & Zip Archive for Function Code
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "function_source_bucket" {
  name                        = "${var.project_id}-agent-remediator-src-${random_id.bucket_suffix.hex}"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "function_zip" {
  type        = "zip"
  output_path = "${path.module}/build/function_source.zip"
  source_dir  = "${path.module}/../cloud_function"
  excludes = [
    ".venv",
    "__pycache__",
    "*.pyc",
    "test_remediator.py",
  ]
}

resource "google_storage_bucket_object" "source_archive" {
  name   = "function-source-${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source_bucket.name
  source = data.archive_file.function_zip.output_path
}

# 4. Cloud Function (Generation 2)
resource "google_cloudfunctions2_function" "remediator" {
  name        = var.function_name
  location    = var.region
  project     = var.project_id
  description = "Auto-remediates agent observability and prompt logging for regulatory compliance"

  build_config {
    runtime     = "python311"
    entry_point = "process_audit_log"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source_bucket.name
        object = google_storage_bucket_object.source_archive.name
      }
    }
  }

  service_config {
    max_instance_count             = 10
    min_instance_count             = 0
    available_memory               = "512Mi"
    timeout_seconds                = 60
    service_account_email          = google_service_account.remediator_sa.email
    ingress_settings               = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true

    environment_variables = {
      ENFORCE_GE_TELEMETRY_LOGGING = tostring(var.enforce_ge_telemetry_logging)
      ENFORCE_GE_PROMPT_LOGGING    = tostring(var.enforce_ge_prompt_logging)
      ENFORCE_DF_TELEMETRY_LOGGING = tostring(var.enforce_df_telemetry_logging)
      ENFORCE_DF_PROMPT_LOGGING    = tostring(var.enforce_df_prompt_logging)
    }
  }

  depends_on = [
    google_project_service.enabled_services,
    google_project_iam_member.dialogflow_admin,
    google_project_iam_member.discoveryengine_editor,
  ]
}

# 5. Allow Eventarc Service Account to invoke the underlying Cloud Run service
resource "google_cloud_run_service_iam_member" "invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.remediator.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.remediator_sa.email}"
}

# 6. Eventarc Trigger: Dialogflow CX Agent Creation & Updates
resource "google_eventarc_trigger" "dialogflow_agent_create" {
  name     = "${var.function_name}-df-create"
  location = var.region
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "dialogflow.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.dialogflow.v3.Agents.CreateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 7. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Engine Creation
resource "google_eventarc_trigger" "discoveryengine_engine_create" {
  name     = "${var.function_name}-ge-create"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1.EngineService.CreateEngine"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 8. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Creation (v1alpha)
resource "google_eventarc_trigger" "discoveryengine_agent_create_v1alpha" {
  name     = "${var.function_name}-ge-agent-create-v1alpha"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1alpha.AgentService.CreateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 9. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Creation (v1)
resource "google_eventarc_trigger" "discoveryengine_agent_create_v1" {
  name     = "${var.function_name}-ge-agent-create-v1"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1.AgentService.CreateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 10. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Update (v1alpha)
resource "google_eventarc_trigger" "discoveryengine_agent_update_v1alpha" {
  name     = "${var.function_name}-ge-agent-update-v1alpha"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1alpha.AgentService.UpdateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 11. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Creation (v1main / Web Console)
resource "google_eventarc_trigger" "discoveryengine_agent_create_v1main" {
  name     = "${var.function_name}-ge-agent-create-v1main"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1main.AgentService.CreateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 12. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Update (v1main / Web Console)
resource "google_eventarc_trigger" "discoveryengine_agent_update_v1main" {
  name     = "${var.function_name}-ge-agent-update-v1main"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1main.AgentService.UpdateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}

# 13. Eventarc Trigger: Discovery Engine (Gemini Enterprise) Agent Update (v1)
resource "google_eventarc_trigger" "discoveryengine_agent_update_v1" {
  name     = "${var.function_name}-ge-agent-update-v1"
  location = "global"
  project  = var.project_id

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "discoveryengine.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = "google.cloud.discoveryengine.v1.AgentService.UpdateAgent"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.remediator.name
      region  = var.region
    }
  }

  service_account = google_service_account.remediator_sa.email
  depends_on      = [google_cloudfunctions2_function.remediator]
}
