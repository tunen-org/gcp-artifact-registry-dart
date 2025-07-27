import os
from flask import Flask, jsonify, request
from data.repositories.artifact_repository_dart_wrapper_repository import (
    PackageRepository,
    PackageNotFoundError,
    PackageRepositoryError,
)
from data.services.artifact_registry_api_service import ArtifactRegistryService


def create_app():
    app = Flask(__name__)

    # Configuration
    PROJECT_ID = os.environ.get("PROJECT_ID")
    LOCATION = os.environ.get("LOCATION", "europe-west1")
    REPOSITORY = os.environ.get("REPOSITORY", "dart-package-repository")

    if not PROJECT_ID:
        raise ValueError("PROJECT_ID environment variable is required")

    # Initialize services
    artifact_service = ArtifactRegistryService(PROJECT_ID, LOCATION, REPOSITORY)
    package_repo = PackageRepository(artifact_service, request.host_url.rstrip("/"))

    @app.route("/api/packages/<package_name>")
    def list_package_versions(package_name):
        """List all versions of a package (Pub Repository Specification v2)"""
        try:
            package = package_repo.get_package(package_name)

            response = {
                "name": package.name,
                "latest": {
                    "version": package.latest.version,
                    "archive_url": package.latest.archive_url,
                    "archive_sha256": package.latest.archive_sha256,
                    "pubspec": package.latest.pubspec,
                },
                "versions": [
                    {
                        "version": version.version,
                        "archive_url": version.archive_url,
                        "archive_sha256": version.archive_sha256,
                        "pubspec": version.pubspec,
                    }
                    for version in package.versions
                ],
            }

            # Add optional fields if present
            if package.is_discontinued:
                response["isDiscontinued"] = True
                if package.replaced_by:
                    response["replacedBy"] = package.replaced_by

            if package.advisories_updated:
                response["advisoriesUpdated"] = package.advisories_updated.isoformat()

            return jsonify(response)

        except PackageNotFoundError:
            return jsonify(
                {
                    "error": {
                        "code": "not_found",
                        "message": f"Package {package_name} not found",
                    }
                }
            ), 404

        except PackageRepositoryError as e:
            return jsonify(
                {"error": {"code": "repository_error", "message": str(e)}}
            ), 500

    @app.route("/api/packages/versions/new")
    def new_package_upload():
        """Get upload URL for publishing packages (Pub Repository Specification v2)"""
        # TODO: Add authentication check
        upload_info = package_repo.get_upload_info()

        return jsonify({"url": upload_info.url, "fields": upload_info.fields})

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

        result = package_repo.upload_package(file_data)

        if result.success:
            return "", 204, {"Location": result.finalize_url}
        else:
            return jsonify(
                {"error": {"code": "upload_failed", "message": result.message}}
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

    # Deprecated endpoints for backward compatibility
    @app.route("/api/packages/<package_name>/versions/<version>")
    def get_package_version(package_name, version):
        """Deprecated: Inspect a specific version of a package"""
        try:
            package = package_repo.get_package(package_name)

            # Find the specific version
            for pkg_version in package.versions:
                if pkg_version.version == version:
                    return jsonify(
                        {
                            "version": pkg_version.version,
                            "archive_url": pkg_version.archive_url,
                            "pubspec": pkg_version.pubspec,
                        }
                    )

            return jsonify(
                {
                    "error": {
                        "code": "version_not_found",
                        "message": f"Version {version} not found for package {package_name}",
                    }
                }
            ), 404

        except PackageNotFoundError:
            return jsonify(
                {
                    "error": {
                        "code": "not_found",
                        "message": f"Package {package_name} not found",
                    }
                }
            ), 404

    return app
