"""
Base classes and data structures for package registry adapters.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional, List
from urllib.parse import urlparse
import logging
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class HostRateLimiter:
    """
    Enforce a minimum interval between requests to the same host.

    Adapters are called from a thread pool, so throttling has to be per host
    rather than a blanket sleep: npm and PyPI have no reason to wait on each
    other, but crates.io does ask for roughly one request per second.
    """

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = defaultdict(float)

    def wait(self, host: str):
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_for = max(0.0, self._next_allowed[host] - now)
            self._next_allowed[host] = max(now, self._next_allowed[host]) + self.min_interval
        # Sleep outside the lock, or every host would queue behind every other.
        if wait_for:
            time.sleep(wait_for)


_session_lock = threading.Lock()
_session = None
_rate_limiter = None

USER_AGENT = "LibTrack-AI/1.0 (dependency update tracker)"


def get_session() -> requests.Session:
    """
    Return the process-wide pooled HTTP session shared by all registry adapters.

    Without pooling every registry call pays a fresh TCP and TLS handshake.
    The session is only ever read by workers (never reconfigured after setup),
    which is the usage requests' connection pooling is safe for.
    """
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                session = requests.Session()
                retry = Retry(
                    total=2,
                    backoff_factor=0.3,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset({"GET", "POST"}),
                    raise_on_status=False,
                )
                adapter = HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=retry)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                session.headers.update({"User-Agent": USER_AGENT})
                _session = session
    return _session


def get_rate_limiter() -> HostRateLimiter:
    """Return the process-wide per-host rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        from django.conf import settings

        with _session_lock:
            if _rate_limiter is None:
                _rate_limiter = HostRateLimiter(
                    getattr(settings, "LIBTRACK_HOST_RATE_LIMIT_SECONDS", 0.25)
                )
    return _rate_limiter


def reset_http_state():
    """Drop the cached session and rate limiter. Tests only."""
    global _session, _rate_limiter
    with _session_lock:
        if _session is not None:
            _session.close()
        _session = None
        _rate_limiter = None


@dataclass
class VersionInfo:
    """
    Standardized version information returned by all registry adapters.
    
    Attributes:
        version: Semantic version string (e.g., "2.2.1")
        release_date: Date when this version was released
        homepage_url: Project homepage URL
        summary: Brief description of the package/library
        source_url: URL to the source where this info was fetched
        trust_level: Confidence level 0-100 (100 = official registry API)
        is_prerelease: Whether this is a pre-release version (alpha, beta, rc)
        changelog_url: Optional URL to changelog/release notes
    """
    version: str
    release_date: Optional[date] # Changed to Optional
    homepage_url: str
    summary: str
    source_url: str
    trust_level: int = 100 # Added default
    is_prerelease: bool = False # Added default
    changelog_url: Optional[str] = None
    
    
    def __post_init__(self):
        """Validate trust level range."""
        if not 0 <= self.trust_level <= 100:
            raise ValueError(f"trust_level must be 0-100, got {self.trust_level}")


@dataclass
class PreReleaseInfo:
    """Standardized information about a detected pre-release."""
    version: str
    release_date: Optional[date]
    prerelease_type: str  # alpha, beta, rc, etc.
    summary: str
    source_url: str
    trust_level: int = 95
    is_published: bool = True  # True if found in registry, False if just a plan
    confirmation_count: int = 1  # Number of independent sources confirming this

    
    def __post_init__(self):
        """Validate trust level range."""
        if not 0 <= self.trust_level <= 100:
            raise ValueError(f"trust_level must be 0-100, got {self.trust_level}")


class PackageRegistry(ABC):
    """
    Abstract base class for package manager registry adapters.
    
    Each registry (PyPI, npm, RubyGems, etc.) should implement this interface
    to provide a consistent way to fetch version information.
    """
    
    def __init__(self, timeout: int = 10, debug: bool = False):
        """
        Initialize registry adapter.
        
        Args:
            timeout: HTTP request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        # Response cache is per thread: one adapter instance is shared across
        # the fetch thread pool, so a plain dict would serve one package's
        # response for another package's request.
        self._local = threading.local()

        if self.debug:
            logger.setLevel(logging.DEBUG)

    @property
    def session(self) -> requests.Session:
        """Pooled session shared across all adapters."""
        return get_session()

    def begin_response_cache(self):
        """
        Start deduplicating identical GETs on this thread.

        Several adapter methods read the same registry endpoint - PyPI's
        ``/pypi/<name>/json`` answers both get_prereleases and
        get_repository_url - so a caller that invokes more than one of them for
        the same package can wrap the pass and pay for a single request.
        """
        self._local.cache = {}

    def end_response_cache(self):
        """Stop deduplicating and drop anything cached on this thread."""
        self._local.cache = None

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Perform a rate-limited, connection-pooled GET.

        Adapters should use this instead of ``requests.get`` so that the
        per-host throttle applies when fetches run concurrently. Repeat calls
        are served from the cache while one is active.
        """
        kwargs.setdefault("timeout", self.timeout)

        cache = getattr(self._local, "cache", None)
        key = None
        if cache is not None:
            params = kwargs.get("params") or {}
            key = (url, tuple(sorted(params.items())))
            if key in cache:
                self._log_debug(f"Cache hit for {url}")
                return cache[key]

        get_rate_limiter().wait(urlparse(url).netloc)
        response = self.session.get(url, **kwargs)

        if cache is not None:
            cache[key] = response
        return response

    def head(self, url: str, **kwargs) -> requests.Response:
        """Perform a rate-limited, connection-pooled HEAD."""
        kwargs.setdefault("timeout", self.timeout)
        get_rate_limiter().wait(urlparse(url).netloc)
        return self.session.head(url, **kwargs)

    @abstractmethod
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
            ValueError: For invalid package names
        """
        pass
    
    @abstractmethod
    def supports_package(self, package_name: str) -> bool:
        """
        Check if this registry can handle the given package.
        
        Args:
            package_name: Name of the package
        
        Returns:
            True if this registry supports this package
        """
        pass
    
    @abstractmethod
    def get_prereleases(self, package_name: str) -> List[PreReleaseInfo]:
        """
        Fetch available PRE-RELEASE versions (beta, rc, etc.) of a package.
        Should return a list of PreReleaseInfo objects.
        """
        pass

    @abstractmethod
    def get_repository_url(self, package_name: str) -> Optional[str]:
        """
        Get the source repository URL (e.g. GitHub) for a package.
        Required for Tier 2 future version detection (Milestones/Releases).
        """
        pass
    
    def _log_debug(self, message: str):
        """Log debug message if debug mode enabled."""
        if self.debug:
            logger.debug(f"[{self.__class__.__name__}] {message}")
    
    def _log_info(self, message: str):
        """Log info message."""
        logger.info(f"[{self.__class__.__name__}] {message}")
    
    def _log_error(self, message: str):
        """Log error message."""
        logger.error(f"[{self.__class__.__name__}] {message}")
