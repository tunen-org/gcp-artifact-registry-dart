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
  default     = "us-central1"
}

# Artifact Registry repository for Dart packages - will be created as a generic repository
variable "artifact_registry_dart_repo_name" {
  description = "The name of the Artifact Registry repository for Dart packages"
  type        = string
  default     = "dart-packages-repository"
}

# Image repository for Cloud Run to store the Dart wrapper api image
variable "artifact_registry_docker_repo_name" {
  description = "The name of the Artifact Registry repository for Docker images used by Cloud Run"
  type        = string
  default     = "artifact-registry-dart-image-repository"
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

# Service Account for Cloud Build
resource "google_service_account" "cloudbuild_sa" {
  account_id   = "artifact-registry-dart-build-cd"
  display_name = "Cloud Build Service Account"
}

# Service Account for Cloud Run
resource "google_service_account" "cloudrun_sa" {
  account_id   = "artifact-registry-dart-run"
  display_name = "Cloud Run Service Account"
}

# IAM bindings for Cloud Build Service Account
resource "google_project_iam_member" "cloudbuild_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

resource "google_project_iam_member" "cloudbuild_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

# IAM bindings for Cloud Run Service Account

# Cloud Build trigger
resource "google_cloudbuild_trigger" "build_trigger_cd" {

  name        = "artifact-registry-dart-cd-trigger"
  description = "Deploy Dart pub server to Cloud Run"

  service_account = google_service_account.cloudbuild_sa.id

  substitutions = {
    _PROJECT_ID                  = var.project_id
    _REGION                      = var.region
    _ARTIFACT_REGISTRY_REPO_NAME = var.artifact_registry_dart_repo_name
    _CLOUDRUN_SA_EMAIL           = google_service_account.cloudrun_sa.email
  }

  filename = "cloudbuild-cd.yaml"
}

# Output values
