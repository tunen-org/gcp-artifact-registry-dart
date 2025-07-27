import os
import tarfile
import hashlib
import requests
from io import BytesIO
from flask import Flask, jsonify, request
from google.auth import default
from google.auth.transport.requests import Request
import yaml

app = Flask(__name__)

# Configuration - these will be set via environment variables
PROJECT_ID = os.environ.get("PROJECT_ID", "your-project-id")
LOCATION = os.environ.get("LOCATION", "us-central1")
REPOSITORY = os.environ.get("REPOSITORY", "dart-packages-repository")


class ArtifactRegistryPubServer:
    def __init__(self, project_id, location, repository):
        self.project_id = project_id
        self.location = location
        self.repository = repository

        # Initialize credentials for REST API calls
        self.credentials, _ = default()
        self.base_url = f"https://artifactregistry.googleapis.com/v1/projects/{project_id}/locations/{location}/repositories/{repository}"

    def _get_access_token(self):
        """Get an access token for API calls"""
        # Always refresh to ensure we have a valid token
        # This is safe to call - it will only refresh if needed
        request = Request()
        self.credentials.refresh(request)
        return self.credentials.token

    def list_package_versions(self, package_name):
        """List all versions of a package from Artifact Registry using REST API"""
        try:
            headers = {
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json",
            }

            # List packages with the specific name
            packages_url = f"{self.base_url}/packages"
            params = {"filter": f"name:packages/{package_name}"}

            response = requests.get(packages_url, headers=headers, params=params)

            if response.status_code != 200:
                print(f"Error listing packages: {response.text}")
                return []

            packages_data = response.json()
            package_versions = []

            for package in packages_data.get("packages", []):
                # List versions for this package
                versions_url = f"{self.base_url}/packages/{package_name}/versions"
                versions_response = requests.get(versions_url, headers=headers)

                if versions_response.status_code == 200:
                    versions_data = versions_response.json()
                    for version in versions_data.get("versions", []):
                        package_versions.append(
                            {
                                "name": package_name,
                                "version": version["name"].split("/")[-1],
                                "create_time": version.get("createTime"),
                                "update_time": version.get("updateTime"),
                            }
                        )

            # Sort by creation time (newest first)
            package_versions.sort(key=lambda x: x["create_time"] or "", reverse=True)
            return package_versions

        except Exception as e:
            print(f"Error listing package versions: {e}")
            return []

    def get_package_file_url(self, package_name, version):
        """Get download URL for a specific package version using REST API"""
        try:
            headers = {
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json",
            }

            # List files in the version
            files_url = (
                f"{self.base_url}/packages/{package_name}/versions/{version}/files"
            )
            response = requests.get(files_url, headers=headers)

            if response.status_code != 200:
                return None

            files_data = response.json()

            for file_info in files_data.get("files", []):
                if file_info["name"].endswith("package.tar.gz"):
                    # Generate download URL
                    file_name = file_info["name"]
                    download_url = f"https://artifactregistry.googleapis.com/download/v1/{file_name}"
                    return download_url

            return None

        except Exception as e:
            print(f"Error getting package file URL: {e}")
            return None

    def upload_package(self, package_data, package_name, version):
        """Upload package to Artifact Registry using REST API"""
        try:
            headers = {"Authorization": f"Bearer {self._get_access_token()}"}

            # Upload using the generic artifacts API
            upload_url = f"https://artifactregistry.googleapis.com/upload/v1/projects/{self.project_id}/locations/{self.location}/repositories/{self.repository}/genericArtifacts:create"

            # Prepare the multipart form data
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

            if response.status_code in [200, 201]:
                return True
            else:
                print(f"Upload failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"Error uploading package: {e}")
            return False

    def download_package(self, package_name, version, filename="package.tar.gz"):
        """Download a package from Artifact Registry using REST API"""
        try:
            headers = {"Authorization": f"Bearer {self._get_access_token()}"}

            # Download using the generic download API
            download_url = f"https://artifactregistry.googleapis.com/download/v1/projects/{self.project_id}/locations/{self.location}/repositories/{self.repository}/packages/{package_name}/versions/{version}/files/{filename}"

            response = requests.get(download_url, headers=headers)

            if response.status_code == 200:
                return response.content
            else:
                print(f"Download failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error downloading package: {e}")
            return None

    def delete_package_file(self, package_name, version, filename="package.tar.gz"):
        """Delete a package file from Artifact Registry using REST API"""
        try:
            headers = {
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json",
            }

            # Get the full file path first
            files_url = (
                f"{self.base_url}/packages/{package_name}/versions/{version}/files"
            )
            response = requests.get(files_url, headers=headers)

            if response.status_code != 200:
                return False

            files_data = response.json()
            file_path = None

            for file_info in files_data.get("files", []):
                if file_info["name"].endswith(filename):
                    file_path = file_info["name"]
                    break

            if not file_path:
                return False

            # Delete the file
            delete_url = f"https://artifactregistry.googleapis.com/v1/{file_path}"
            response = requests.delete(delete_url, headers=headers)

            return response.status_code in [200, 204]

        except Exception as e:
            print(f"Error deleting package file: {e}")
            return False

    def get_package_metadata(self, package_name, version):
        """Get package metadata including pubspec and SHA256"""
        try:
            # Download the package to extract metadata
            package_data = self.download_package(package_name, version)

            if not package_data:
                return None

            # Extract pubspec
            pubspec = self.extract_pubspec_from_archive(package_data)

            # Calculate SHA256
            sha256 = self.calculate_sha256(package_data)

            return {
                "pubspec": pubspec,
                "archive_sha256": sha256,
                "size": len(package_data),
            }

        except Exception as e:
            print(f"Error getting package metadata: {e}")
            return None

    def extract_pubspec_from_archive(self, archive_data):
        """Extract pubspec.yaml from the tar.gz archive"""
        try:
            with tarfile.open(fileobj=BytesIO(archive_data), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("pubspec.yaml"):
                        pubspec_file = tar.extractfile(member)
                        if pubspec_file:
                            content = pubspec_file.read().decode("utf-8")
                            return yaml.safe_load(content)
            return {}
        except Exception as e:
            print(f"Error extracting pubspec: {e}")
            return {}

    def calculate_sha256(self, data):
        """Calculate SHA256 hash of data"""
        return hashlib.sha256(data).hexdigest()


# Initialize the server
pub_server = ArtifactRegistryPubServer(PROJECT_ID, LOCATION, REPOSITORY)


@app.route("/api/packages/<package_name>")
def list_package_versions(package_name):
    """Implement: List all versions of a package"""
    versions = pub_server.list_package_versions(package_name)

    if not versions:
        return jsonify(
            {"error": {"code": "not_found", "message": "Package not found"}}
        ), 404

    # Transform Artifact Registry response to Pub format
    latest_version = versions[0] if versions else None

    # Get metadata for the latest version
    latest_metadata = (
        pub_server.get_package_metadata(package_name, latest_version["version"])
        if latest_version
        else {}
    )
    if latest_metadata is None:
        latest_metadata = {}

    response = {
        "name": package_name,
        "latest": {
            "version": latest_version["version"] if latest_version else "",
            "archive_url": pub_server.get_package_file_url(
                package_name, latest_version["version"]
            )
            if latest_version
            else "",
            "archive_sha256": latest_metadata.get("archive_sha256", ""),
            "pubspec": latest_metadata.get("pubspec", {}),
        },
        "versions": [],
    }

    for version in versions:
        metadata = pub_server.get_package_metadata(package_name, version["version"])
        response["versions"].append(
            {
                "version": version["version"],
                "archive_url": pub_server.get_package_file_url(
                    package_name, version["version"]
                ),
                "archive_sha256": metadata.get("archive_sha256", "")
                if metadata
                else "",
                "pubspec": metadata.get("pubspec", {}) if metadata else {},
            }
        )

    return jsonify(response)


@app.route("/api/packages/versions/new")
def new_package_upload():
    """Implement: Publishing Packages - Get upload URL"""
    # In a real implementation, you'd generate a signed upload URL
    # For simplicity, we'll use a direct upload endpoint
    return jsonify(
        {
            "url": f"{request.host_url}upload",
            "fields": {
                "token": "your-upload-token"  # Add authentication
            },
        }
    )


@app.route("/upload", methods=["POST"])
def upload_package():
    """Handle package upload"""
    file = request.files.get("file")
    if not file:
        return jsonify(
            {"error": {"code": "missing_file", "message": "No file provided"}}
        ), 400

    # Read file data
    file_data = file.read()

    # Extract package name and version from pubspec.yaml in the archive
    pubspec = pub_server.extract_pubspec_from_archive(file_data)

    if not pubspec:
        return jsonify(
            {
                "error": {
                    "code": "invalid_package",
                    "message": "Could not extract pubspec.yaml",
                }
            }
        ), 400

    package_name = pubspec.get("name")
    version = pubspec.get("version")

    if not package_name or not version:
        return jsonify(
            {
                "error": {
                    "code": "invalid_pubspec",
                    "message": "Missing name or version in pubspec.yaml",
                }
            }
        ), 400

    success = pub_server.upload_package(file_data, package_name, version)

    if success:
        return (
            "",
            204,
            {"Location": f"{request.host_url}finalize/{package_name}/{version}"},
        )
    else:
        return jsonify(
            {"error": {"code": "upload_failed", "message": "Upload failed"}}
        ), 500


@app.route("/finalize/<package_name>/<version>")
def finalize_upload(package_name, version):
    """Finalize package upload"""
    return jsonify(
        {
            "success": {
                "message": f"Package {package_name} version {version} published successfully"
            }
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
