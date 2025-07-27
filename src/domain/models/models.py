from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime


@dataclass
class PackageVersion:
    """Domain model for a package version"""

    name: str
    version: str
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    archive_url: Optional[str] = None
    archive_sha256: Optional[str] = None
    pubspec: Optional[Dict[str, Any]] = None
    retracted: bool = False


@dataclass
class PackageMetadata:
    """Domain model for package metadata"""

    pubspec: Dict[str, Any]
    archive_sha256: str
    size: int


@dataclass
class Package:
    """Domain model for a complete package with all versions"""

    name: str
    latest: PackageVersion
    versions: List[PackageVersion]
    is_discontinued: bool = False
    replaced_by: Optional[str] = None
    advisories_updated: Optional[datetime] = None


@dataclass
class UploadInfo:
    """Domain model for package upload information"""

    url: str
    fields: Dict[str, str]


@dataclass
class UploadResult:
    """Domain model for upload result"""

    success: bool
    message: str
    finalize_url: Optional[str] = None
