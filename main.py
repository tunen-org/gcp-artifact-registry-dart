import os
import yaml
import tempfile
import tarfile
import hashlib
from io import BytesIO
from flask import Flask, jsonify, request
from google.cloud import artifactregistry

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

        # Initialize the Artifact Registry client
        self.client = artifactregistry.ArtifactRegistryClient()
        self.repository_path = self.client.repository_path(
            project_id, location, repository
        )

    def list_package_versions(self, package_name):
        """List all versions of a package from Artifact Registry"""
        try:
            # List packages with the specific name
            request = artifactregistry.ListPackagesRequest(
                parent=self.repository_path, filter=f"name:packages/{package_name}"
            )

            packages = self.client.list_packages(request=request)
            package_versions = []

            for package in packages:
                # List versions for this package
                versions_request = artifactregistry.ListVersionsRequest(
                    parent=package.name
                )

                versions = self.client.list_versions(request=versions_request)
                for version in versions:
                    package_versions.append(
                        {
                            "name": package_name,
                            "version": version.name.split("/")[-1],
                            "create_time": version.create_time,
                            "update_time": version.update_time,
                        }
                    )

            # Sort by creation time (newest first)
            package_versions.sort(key=lambda x: x["create_time"], reverse=True)
            return package_versions

        except Exception as e:
            print(f"Error listing package versions: {e}")
            return []

    def get_package_file_url(self, package_name, version):
        """Get download URL for a specific package version"""
        try:
            # Generate a signed URL for the package file
            # Note: This requires the package to be stored with a specific structure
            version_path = self.client.version_path(
                self.project_id, self.location, self.repository, package_name, version
            )

            # List files in the version
            files_request = artifactregistry.ListFilesRequest(parent=version_path)

            files = self.client.list_files(request=files_request)
            for file in files:
                if file.name.endswith("package.tar.gz"):
                    # Generate download URL
                    # This is a simplified approach - in practice you might want to use signed URLs
                    return f"https://artifactregistry.googleapis.com/download/v1/{file.name}"

            return None

        except Exception as e:
            print(f"Error getting package file URL: {e}")
            return None

    def upload_package(self, package_data, package_name, version):
        """Upload package to Artifact Registry"""
        try:
            # Create a temporary file for the package
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                tmp.write(package_data)
                tmp_path = tmp.name

            try:
                # Upload the file to Artifact Registry
                # Note: This is a simplified approach. The actual implementation
                # would depend on how you structure your generic artifacts

                # For generic repositories, you typically upload using the REST API
                # or by creating the appropriate package/version/file structure

                package_path = self.client.package_path(
                    self.project_id, self.location, self.repository, package_name
                )

                # Check if package exists, create if not
                try:
                    self.client.get_package(name=package_path)
                except:
                    # Package doesn't exist, create it
                    package = artifactregistry.Package(name=package_path)
                    create_package_request = artifactregistry.CreatePackageRequest(
                        parent=self.repository_path,
                        package_id=package_name,
                        package=package,
                    )
                    self.client.create_package(request=create_package_request)

                # Create version
                version_path = self.client.version_path(
                    self.project_id,
                    self.location,
                    self.repository,
                    package_name,
                    version,
                )

                version_obj = artifactregistry.Version(name=version_path)
                create_version_request = artifactregistry.CreateVersionRequest(
                    parent=package_path, version_id=version, version=version_obj
                )

                try:
                    self.client.create_version(request=create_version_request)
                except:
                    pass  # Version might already exist

                # For file upload, you would typically use the REST API
                # or upload to a storage bucket that Artifact Registry monitors

                return True

            finally:
                os.unlink(tmp_path)

        except Exception as e:
            print(f"Error uploading package: {e}")
            return False

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
    response = {
        "name": package_name,
        "latest": {
            "version": latest_version["version"],
            "archive_url": pub_server.get_package_file_url(
                package_name, latest_version["version"]
            ),
            "archive_sha256": "...",  # You can calculate this from the actual file
            "pubspec": {},  # Extract from package
        },
        "versions": [],
    }

    for version in versions:
        response["versions"].append(
            {
                "version": version["version"],
                "archive_url": pub_server.get_package_file_url(
                    package_name, version["version"]
                ),
                "archive_sha256": "...",  # Calculate from file
                "pubspec": {},  # Extract from package
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
