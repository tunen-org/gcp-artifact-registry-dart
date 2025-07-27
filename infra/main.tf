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

# Artifact Registry repository for Dart packages - will be created as a generic repository
variable "artifact_registry_dart_repo_name" {
  description = "The name of the Artifact Registry repository for Dart packages"
  type        = string
  default     = "gcp-artifact-registry-dart-packages-repository"
}

# Image repository for Cloud Run to store the Dart wrapper api image
variable "artifact_registry_docker_repo_name" {
  description = "The name of the Artifact Registry repository for Docker images used by Cloud Run"
  type        = string
  default     = "gcp-artifact-registry-dart-image-repository"
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

# Create the Docker Artifact Registry repository
resource "google_artifact_registry_repository" "docker_repository" {
  location      = var.region
  repository_id = var.artifact_registry_docker_repo_name
  description   = "Docker images repository for Dart wrapper API"
  format        = "DOCKER"
}

# Service Account for Cloud Build
resource "google_service_account" "cloudbuild_sa" {
  account_id   = "gcp-ar-dart-build-cd"
  display_name = "Cloud Build Service Account"
}

# Service Account for Cloud Run
resource "google_service_account" "cloudrun_sa" {
  account_id   = "gcp-ar-dart-run"
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

resource "google_project_iam_member" "cloudbuild_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
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

# Cloud Build trigger for Continuous Deployment
resource "google_cloudbuild_trigger" "build_trigger_cd" {

  name        = "artifact-registry-dart-cd-trigger"
  description = "Deploy Dart pub server to Cloud Run"
  location    = var.region

  # TODO: This will need tp be a variable or parameterized
  repository_event_config {
    repository = "projects/tunen-norman-dev/locations/europe-west1/connections/tunen-github/repositories/tunen-org-gcp-artifact-registry-dart"

  }

  service_account = google_service_account.cloudbuild_sa.id

  substitutions = {
    _PROJECT_ID                       = var.project_id
    _REGION                           = var.region
    _ARTIFACT_REGISTRY_DART_REPO_NAME = var.artifact_registry_dart_repo_name
    _CLOUDRUN_SA_EMAIL                = google_service_account.cloudrun_sa.email
  }

  filename = "cloudbuild-cd.yaml"
}

# Output values
