"""
LibTrack AI Services Package

This package contains the core service classes for LibTrack AI:

1. **LibrarySyncService**: Syncs StackComponents to central Library entities
2. **VersionFetchService**: Fetches latest versions from registries/web
3. **FutureUpdateService**: Detects and manages upcoming releases
4. **SecurityVulnerabilityService**: Detects known vulnerabilities via OSV
5. **NotificationService**: Sends update notifications to projects

The services are designed to be:
- **Modular**: Each service has a single responsibility
- **Testable**: Services have clear inputs/outputs
- **Reusable**: Can be used from command, celery tasks, or API endpoints
- **Configurable**: Settings passed in __init__
"""

from .library_sync_service import LibrarySyncService
from .version_fetch_service import VersionFetchService
from .future_update_service import FutureUpdateService
from .security_vulnerability_service import SecurityVulnerabilityService
from .notification_service import NotificationService

__all__ = [
    "LibrarySyncService",
    "VersionFetchService",
    "FutureUpdateService",
    "SecurityVulnerabilityService",
    "NotificationService",
]
