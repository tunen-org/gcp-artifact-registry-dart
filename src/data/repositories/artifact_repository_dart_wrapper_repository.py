import tarfile
import hashlib
import yaml
from typing import Optional, Dict
from io import BytesIO
from datetime import datetime

from data.services.artifact_registry_api_service import ArtifactRegistryService
from domain.models.models import (
    Package,
    PackageVersion,
    PackageMetadata,
    UploadInfo,
    UploadResult,
)
from src.domain.models.exceptions import PackageNotFoundError


class PackageRepository:
    """Repository layer that handles business logic and domain model conversion"""

    def __init__(self, artifact_service: ArtifactRegistryService, base_url: str):
        self.artifact_service = artifact_service
        self.base_url = base_url

    def get_package(self, package_name: str) -> Package:
        """Get complete package information with all versions"""
        try:
            versions_data = self.artifact_service.list_package_versions(package_name)
        except Exception as e:
            if "404" in str(e):
                raise PackageNotFoundError(f"Package {package_name} not found")
            raise Exception(f"Failed to retrieve package {package_name}: {e}")

        if not versions_data:
            raise PackageNotFoundError(f"Package {package_name} not found")

        # Sort by creation time (newest first)
        versions_data.sort(key=lambda x: x.get("create_time") or "", reverse=True)

        # Convert to domain models
        versions = []
        for version_data in versions_data:
            try:
                metadata = self._get_package_metadata(
                    package_name, version_data["version"]
                )

                version = PackageVersion(
                    name=package_name,
                    version=version_data["version"],
                    create_time=self._parse_datetime(version_data.get("create_time")),
                    update_time=self._parse_datetime(version_data.get("update_time")),
                    archive_url=self._get_download_url(
                        package_name, version_data["version"]
                    ),
                    archive_sha256=metadata.archive_sha256 if metadata else "",
                    pubspec=metadata.pubspec if metadata else {},
                    retracted=False,  # TODO: Implement retraction logic if needed
                )
                versions.append(version)
            except Exception as e:
                # Log error but continue with other versions
                print(f"Error processing version {version_data['version']}: {e}")
                continue

        if not versions:
            raise Exception(f"No valid versions found for package {package_name}")

        latest = versions[0]

        return Package(name=package_name, latest=latest, versions=versions)

    def upload_package(self, package_data: bytes) -> UploadResult:
        """Upload a package archive"""
        try:
            # Extract package metadata
            pubspec = self._extract_pubspec_from_archive(package_data)

            if not pubspec:
                return UploadResult(
                    success=False, message="Could not extract pubspec.yaml from archive"
                )

            package_name = pubspec.get("name")
            version = pubspec.get("version")

            if not package_name or not version:
                return UploadResult(
                    success=False, message="Missing name or version in pubspec.yaml"
                )

            # Upload to Artifact Registry
            self.artifact_service.upload_package(package_data, package_name, version)

            finalize_url = f"{self.base_url}/finalize/{package_name}/{version}"

            return UploadResult(
                success=True,
                message=f"Package {package_name} version {version} uploaded successfully",
                finalize_url=finalize_url,
            )

        except Exception as e:
            return UploadResult(success=False, message=f"Upload failed: {e}")

    def get_upload_info(self) -> UploadInfo:
        """Get upload information for publishing packages"""
        return UploadInfo(
            url=f"{self.base_url}/upload",
            fields={
                "token": "your-upload-token"
            },  # TODO: Implement proper token generation
        )

    def _get_package_metadata(
        self, package_name: str, version: str
    ) -> Optional[PackageMetadata]:
        """Get package metadata including pubspec and SHA256"""
        try:
            package_data = self.artifact_service.download_package_file(
                package_name, version
            )

            if not package_data:
                return None

            pubspec = self._extract_pubspec_from_archive(package_data)
            sha256 = self._calculate_sha256(package_data)

            return PackageMetadata(
                pubspec=pubspec, archive_sha256=sha256, size=len(package_data)
            )

        except Exception as e:
            print(f"Error getting package metadata for {package_name}:{version}: {e}")
            return None

    def _get_download_url(self, package_name: str, version: str) -> str:
        """Generate download URL for a package version"""
        return f"https://artifactregistry.googleapis.com/download/v1/projects/{self.artifact_service.project_id}/locations/{self.artifact_service.location}/repositories/{self.artifact_service.repository}/packages/{package_name}/versions/{version}/files/package.tar.gz"

    def _extract_pubspec_from_archive(self, archive_data: bytes) -> Dict:
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

    def _calculate_sha256(self, data: bytes) -> str:
        """Calculate SHA256 hash of data"""
        return hashlib.sha256(data).hexdigest()

    def _parse_datetime(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from API response"""
        if not date_string:
            return None
        try:
            # Handle RFC3339 format from Google APIs
            return datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        except Exception:
            return None
