# Terraform configuration for GCP Artifact Registry Dart wrapper
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Variables
variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "europe-west1"
}

# Artifact Registry repository for Dart packages - will be created as a generic repository which will work with Pub through the Dart wrapper
variable "artifact_registry_dart_repo_name" {
  description = "The name of the Artifact Registry repository for Dart packages"
  type        = string
  default     = "dart-package-repository"
}

variable "cloud_run_service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "dart-pub-server"
}

# Configure the Google Cloud provider
provider "google" {
  project = var.project_id
  region  = var.region
}

# Create the generic Artifact Registry repository
resource "google_artifact_registry_repository" "dart_repository" {
  location      = var.region
  repository_id = var.artifact_registry_dart_repo_name
  description   = "Private Dart packages repository"
  format        = "GENERIC"
}

# Service Account for Cloud Run
resource "google_service_account" "cloudrun_sa" {
  account_id   = "gcp-ar-dart-run"
  display_name = "Cloud Run Service Account"
}

# IAM bindings for Cloud Run Service Account
resource "google_project_iam_member" "cloudrun_artifact_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

resource "google_project_iam_member" "cloudrun_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

# Cloud Run service
resource "google_cloud_run_v2_service" "dart_pub_server" {
  name     = var.cloud_run_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloudrun_sa.email

    scaling {
      max_instance_count = 1
      min_instance_count = 0
    }

    containers {
      image = "ghcr.io/tunen-org/gcp-artifact-registry-dart:sha256-ee3f110a2a642d81db9d023871208fb3df4b0f5d36ee62400d06784e1bb2b2d2"

      ports {
        container_port = 5000
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "LOCATION"
        value = var.region
      }

      env {
        name  = "REPOSITORY"
        value = var.artifact_registry_dart_repo_name
      }
    }
  }

  depends_on = [google_artifact_registry_repository.dart_repository]
}

# Make the Cloud Run service publicly accessible
resource "google_cloud_run_v2_service_iam_binding" "public_access" {
  location = google_cloud_run_v2_service.dart_pub_server.location
  name     = google_cloud_run_v2_service.dart_pub_server.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# Output values
output "cloud_run_url" {
  description = "URL of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.dart_pub_server.uri
}

output "artifact_registry_repository_name" {
  description = "Name of the Artifact Registry repository"
  value       = google_artifact_registry_repository.dart_repository.name
}
