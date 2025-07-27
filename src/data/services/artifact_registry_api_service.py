import requests
from typing import List, Optional, Dict, Any
from google.auth import default
from google.auth.transport.requests import Request
from io import BytesIO


class ArtifactRegistryService:
    """Service layer for making REST API requests to Google Cloud Artifact Registry"""

    def __init__(self, project_id: str, location: str, repository: str):
        self.project_id = project_id
        self.location = location
        self.repository = repository

        # Initialize credentials for REST API calls
        self.credentials, _ = default()
        self.base_url = f"https://artifactregistry.googleapis.com/v1/projects/{project_id}/locations/{location}/repositories/{repository}"

    def _get_access_token(self) -> str:
        """Get an access token for API calls"""
        request = Request()
        self.credentials.refresh(request)
        return self.credentials.token

    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for API requests"""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def list_package_versions(self, package_name: str) -> List[Dict[str, Any]]:
        """List all versions of a package from Artifact Registry"""
        headers = self._get_headers()

        # List packages with the specific name
        packages_url = f"{self.base_url}/packages"
        params = {"filter": f"name:packages/{package_name}"}

        response = requests.get(packages_url, headers=headers, params=params)
        response.raise_for_status()

        packages_data = response.json()
        package_versions = []

        for package in packages_data.get("packages", []):
            # List versions for this package
            versions_url = f"{self.base_url}/packages/{package_name}/versions"
            versions_response = requests.get(versions_url, headers=headers)
            versions_response.raise_for_status()

            versions_data = versions_response.json()
            for version in versions_data.get("versions", []):
                package_versions.append(
                    {
                        "name": package_name,
                        "version": version["name"].split("/")[-1],
                        "create_time": version.get("createTime"),
                        "update_time": version.get("updateTime"),
                        "full_name": version["name"],
                    }
                )

        return package_versions

    def get_package_files(
        self, package_name: str, version: str
    ) -> List[Dict[str, Any]]:
        """Get files for a specific package version"""
        headers = self._get_headers()

        files_url = f"{self.base_url}/packages/{package_name}/versions/{version}/files"
        response = requests.get(files_url, headers=headers)
        response.raise_for_status()

        return response.json().get("files", [])

    def download_package_file(
        self, package_name: str, version: str, filename: str = "package.tar.gz"
    ) -> Optional[bytes]:
        """Download a package file from Artifact Registry"""
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}

        download_url = f"https://artifactregistry.googleapis.com/download/v1/projects/{self.project_id}/locations/{self.location}/repositories/{self.repository}/packages/{package_name}/versions/{version}/files/{filename}"

        response = requests.get(download_url, headers=headers)
        response.raise_for_status()

        return response.content

    def upload_package(
        self, package_data: bytes, package_name: str, version: str
    ) -> bool:
        """Upload package to Artifact Registry"""
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}

        upload_url = f"https://artifactregistry.googleapis.com/upload/v1/projects/{self.project_id}/locations/{self.location}/repositories/{self.repository}/genericArtifacts:create"

        files = {
            "meta": (
                None,
                f'{{"filename":"package.tar.gz","package_id":"{package_name}","version_id":"{version}"}}',
                "application/json",
            ),
            "blob": ("package.tar.gz", BytesIO(package_data), "application/gzip"),
        }

        params = {"alt": "json"}

        response = requests.post(
            upload_url, headers=headers, files=files, params=params
        )
        response.raise_for_status()

        return True

    def delete_package_file(
        self, package_name: str, version: str, filename: str = "package.tar.gz"
    ) -> bool:
        """Delete a package file from Artifact Registry"""
        headers = self._get_headers()

        # Get the full file path first
        files = self.get_package_files(package_name, version)

        file_path = None
        for file_info in files:
            if file_info["name"].endswith(filename):
                file_path = file_info["name"]
                break

        if not file_path:
            raise FileNotFoundError(
                f"File {filename} not found for {package_name}:{version}"
            )

        delete_url = f"https://artifactregistry.googleapis.com/v1/{file_path}"
        response = requests.delete(delete_url, headers=headers)
        response.raise_for_status()

        return True
