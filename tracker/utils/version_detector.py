"""
Version detection orchestrator using hierarchical 3-tier strategy.

Tier 1: Official package manager APIs (PyPI, npm, etc.)
Tier 2: GitHub Releases API (for known repositories)
Tier 3: Serper + Groq fallback (last resort)
"""

import logging
from typing import Optional
from datetime import datetime

from tracker.utils.registry_adapters import (
    VersionInfo,
    PyPIRegistry,
    NpmRegistry,
    RubyGemsRegistry,
    CargoRegistry,
    NuGetRegistry,
    MavenRegistry,
)
from tracker.utils.version_validator import VersionValidator

logger = logging.getLogger(__name__)


class VersionDetector:
    """
    Orchestrates version detection using a 3-tier hierarchical strategy.
    
    Strategy:
    1. Try official package manager API (100% trust, fast, free)
    2. Try GitHub Releases API (95% trust, if repo known)
    3. Fallback to Serper + Groq (40-70% trust, slow, costly)
    
    This maximizes accuracy while minimizing API costs and latency.
    """
    
    def __init__(self, timeout: int = 10, debug: bool = False):
        """
        Initialize version detector with all registry adapters.
        
        Args:
            timeout: HTTP timeout for API calls
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        
        # Initialize all registry adapters
        self.registries = {
            "pypi": PyPIRegistry(timeout=timeout, debug=debug),
            "npm": NpmRegistry(timeout=timeout, debug=debug),
            "rubygems": RubyGemsRegistry(timeout=timeout, debug=debug),
            "cargo": CargoRegistry(timeout=timeout, debug=debug),
            "nuget": NuGetRegistry(timeout=timeout, debug=debug),
            "maven": MavenRegistry(timeout=timeout, debug=debug),
        }
        
        self.validator = VersionValidator()
        
        # Lazy-load Serper/Groq only if needed (fallback)
        self._serper = None
        self._groq = None
        
        if debug:
            logger.setLevel(logging.DEBUG)
    
    def detect_version(
        self,
        library_name: str,
        component_type: str = "library",
        current_version: Optional[str] = None,
        registry_hint: Optional[str] = None,
    ) -> Optional[VersionInfo]:
        """
        Detect the latest version of a library using hierarchical strategy.
        
        Args:
            library_name: Name of the library/package
            component_type: Type of component ("library", "language", "tool")
            current_version: Current version to compare against
            registry_hint: Optional registry type hint ("pypi", "npm", etc.)
        
        Returns:
            VersionInfo if found, None otherwise
        """
        logger.info(f"🔍 Detecting version for {library_name} (type: {component_type})")
        
        # TIER 1: Official Package Manager APIs
        version_info = self._try_official_registries(
            library_name, 
            component_type, 
            registry_hint
        )
        
        if version_info:
            # Validate the version
            if not self.validator.is_valid_semantic_version(version_info.version):
                logger.warning(f"Invalid version format from registry: {version_info.version}")
                return None
            
            # Check if newer than current
            if current_version:
                if not self.validator.is_newer(version_info.version, current_version):
                    logger.info(
                        f"Version {version_info.version} not newer than current {current_version}"
                    )
                    return None
            
            logger.info(
                f"✅ Found {library_name} v{version_info.version} "
                f"(trust: {version_info.trust_level}%)"
            )
            return version_info
        
        # TIER 2: GitHub Releases API
        # Handled dynamically via Serper discovery in fallback method below
        # since we don't always know the repo URL upfront.
        
        
        # TIER 3: Serper + Groq (fallback)
        logger.warning(f"⚠️ Falling back to Serper+Groq for {library_name}")
        return self._fallback_to_serper_groq(library_name, component_type, current_version)
    
    def _try_official_registries(
        self,
        library_name: str,
        component_type: str,
        registry_hint: Optional[str] = None,
    ) -> Optional[VersionInfo]:
        """
        Try official package manager registries.
        
        Args:
            library_name: Package name
            component_type: Component type
            registry_hint: Optional hint about which registry to try first
        
        Returns:
            VersionInfo if found, None otherwise
        """
        # If we have a hint, try that registry first
        if registry_hint and registry_hint in self.registries:
            logger.debug(f"Trying hinted registry: {registry_hint}")
            try:
                result = self.registries[registry_hint].get_latest_version(library_name)
                if result:
                    logger.info(f"✅ Found via {registry_hint} (hinted)")
                    return result
            except Exception as e:
                logger.error(f"Error querying {registry_hint}: {e}")
        
        # Auto-detect based on package name patterns
        detected_registry = self._detect_registry_from_name(library_name)
        if detected_registry and detected_registry != registry_hint:
            logger.debug(f"Auto-detected registry: {detected_registry}")
            try:
                result = self.registries[detected_registry].get_latest_version(library_name)
                if result:
                    logger.info(f"✅ Found via {detected_registry} (auto-detected)")
                    return result
            except Exception as e:
                logger.error(f"Error querying {detected_registry}: {e}")
        
        # Try remaining registries in priority order
        priority_order = ["pypi", "npm", "rubygems", "nuget", "cargo", "maven"]
        
        for registry_name in priority_order:
            # Skip if already tried
            if registry_name == registry_hint or registry_name == detected_registry:
                continue
            
            logger.debug(f"Trying {registry_name}...")
            try:
                result = self.registries[registry_name].get_latest_version(library_name)
                if result:
                    logger.info(f"✅ Found via {registry_name} (fallthrough)")
                    return result
            except Exception as e:
                logger.debug(f"Not found in {registry_name}: {e}")
                continue
        
        logger.warning(f"❌ Not found in any official registry")
        return None
    
    def _detect_registry_from_name(self, package_name: str) -> Optional[str]:
        """
        Auto-detect registry type from package name patterns.
        
        Args:
            package_name: Package name
        
        Returns:
            Registry name or None
        """
        # Scoped npm packages (@vue/cli, @types/node)
        if package_name.startswith("@"):
            return "npm"
        
        # Maven coordinates (groupId:artifactId)
        if ":" in package_name:
            return "maven"
        
        # No clear pattern
        return None
    
    def _fallback_to_serper_groq(
        self,
        library_name: str,
        component_type: str,
        current_version: Optional[str],
    ) -> Optional[VersionInfo]:
        """
        Fallback to Serper + Groq when official APIs fail.
        
        This is the existing method but with lower trust level.
        Also attempts to upgrade to Tier 2 (GitHub API) if a repo URL is found.
        """
        try:
            # Lazy-load Serper and Groq
            if self._serper is None:
                from tracker.utils.serper_fetcher import SerperFetcher
                self._serper = SerperFetcher(timeout=self.timeout, debug=self.debug)
            
            if self._groq is None:
                from tracker.utils.groq_analyzer import GroqAnalyzer
                self._groq = GroqAnalyzer()
            
            # Use existing Serper+Groq flow
            serper_results = self._serper.search_library(
                library_name, 
                current_version, 
                component_type=component_type
            )
            
            # TIER 2 ATTEMPT: Check for GitHub URL in search results
            # If we find a GitHub link, we can use the high-trust GitHub API
            # instead of relying on LLM parsing.
            github_url = self._extract_github_url_from_results(serper_results)
            if github_url:
                logger.info(f"found GitHub URL in search results: {github_url}. Attempting Tier 2 detection.")
                from tracker.utils.github_fetcher import GitHubFetcher
                gh_fetcher = GitHubFetcher()
                gh_version = gh_fetcher.get_latest_stable_version(github_url)
                
                if gh_version:
                    # Validate version
                     if self.validator.is_valid_semantic_version(gh_version.version):
                         # If current_version provided, ensure it's newer
                         if not current_version or self.validator.is_newer(gh_version.version, current_version):
                             logger.info(f"✅ Found {library_name} v{gh_version.version} via GitHub API (Tier 2)")
                             return gh_version

            analysis = self._groq.analyze(library_name, serper_results)
            
            if analysis and not analysis.get("error"):
                # Convert to VersionInfo format
                return self._convert_groq_to_version_info(analysis)
            
            return None
            
        except Exception as e:
            logger.error(f"Serper+Groq fallback failed: {e}")
            return None

    def _extract_github_url_from_results(self, serper_results: dict) -> Optional[str]:
        """Extract the most relevant GitHub URL from search results."""
        results = serper_results.get("results", [])
        for result in results:
            link = result.get("link", "")
            if "github.com" in link:
                # Basic validation: github.com/owner/repo
                parts = link.split('/')
                if len(parts) >= 5:
                    return link
        return None
    
    def _convert_groq_to_version_info(self, analysis: dict) -> Optional[VersionInfo]:
        """
        Convert Groq analysis result to VersionInfo format.
        
        Args:
            analysis: Groq analysis dict
        
        Returns:
            VersionInfo or None
        """
        version = analysis.get("version", "")
        if not version:
            return None
        
        # Parse release date
        release_date_str = analysis.get("release_date", "")
        try:
            if release_date_str and release_date_str != "Not Confirmed":
                release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
            else:
                release_date = datetime.now().date()
        except:
            release_date = datetime.now().date()
        
        return VersionInfo(
            version=version,
            release_date=release_date,
            homepage_url="",
            summary=analysis.get("summary", ""),
            source_url=analysis.get("source", ""),
            trust_level=analysis.get("confidence", 50),  # Lower trust from Groq
            is_prerelease=analysis.get("category") == "future",
            changelog_url=None,
        )
