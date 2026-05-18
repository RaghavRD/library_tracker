"""
Future version detection orchestrator.

Combines results from Package Registries (Tier 1) and GitHub Ecosystem (Tier 2)
to identify upcoming versions, release candidates, and milestones.
"""

import logging
from typing import List, Dict, Optional, Set
from datetime import datetime

# Registries
from tracker.utils.registry_adapters import (
    PyPIRegistry,
    NpmRegistry,
    RubyGemsRegistry,
    CargoRegistry,
    NuGetRegistry,
    MavenRegistry,
    PreReleaseInfo
)

# GitHub
from tracker.utils.github_fetcher import GitHubFetcher

# Shared logic
from tracker.utils.future_version_validator import FutureVersionValidator
from tracker.utils.version_validator import VersionValidator # For semantic sorting

logger = logging.getLogger(__name__)

class FutureVersionDetector:
    """
    Orchestrates detection of future/pre-release versions.
    """
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        
        # Initialize registries
        self.registries = {
            "pypi": PyPIRegistry(timeout=timeout),
            "npm": NpmRegistry(timeout=timeout),
            "rubygems": RubyGemsRegistry(timeout=timeout),
            "cargo": CargoRegistry(timeout=timeout),
            "nuget": NuGetRegistry(timeout=timeout),
            "maven": MavenRegistry(timeout=timeout),
        }
        
        self.github = GitHubFetcher()
        self.validator = VersionValidator()

    def detect_future_versions(
        self, 
        library_name: str, 
        current_version: str,
        registry_type: Optional[str] = None
    ) -> List[PreReleaseInfo]:
        """
        Detect all potential future versions.
        
        Returns:
            List of unique PreReleaseInfo objects, sorted by version (newest first).
        """
        candidates: List[PreReleaseInfo] = []
        
        # 1. Determine which registry to use
        registry_key = registry_type or self._detect_registry(library_name)
        if not registry_key or registry_key not in self.registries:
            logger.warning(f"Could not determine registry for {library_name}")
            return []
            
        registry = self.registries[registry_key]
        
        # 2. Get Registry Pre-releases (Tier 1)
        try:
            reg_updates = registry.get_prereleases(library_name)
            for u in reg_updates:
                u.detection_method = "registry_prerelease"
            candidates.extend(reg_updates)
        except Exception as e:
            logger.error(f"Error fetching registry pre-releases: {e}")
            
        # 3. Get GitHub Updates (Tier 2)
        try:
            repo_url = registry.get_repository_url(library_name)
            if repo_url:
                gh_updates = self.github.get_future_versions(repo_url)
                for u in gh_updates:
                    # Enrich detection type if not set
                    if not hasattr(u, 'detection_method'): 
                        u.detection_method = "github_ecosystem"
                candidates.extend(gh_updates)
        except Exception as e:
            logger.error(f"Error fetching GitHub future versions: {e}")
            
        # 4. Filter and Deduplicate
        unique_versions = self._deduplicate(candidates)
        
        # 5. Filter out versions older than current stable
        # (We only care about *future* versions)
        future_versions = [
            v for v in unique_versions 
            if self.validator.is_newer(v.version, current_version)
        ]
        
        # 6. Calculate Score for each
        for v in future_versions:
            # Re-calculate score to be safe (or update if needed)
            v.trust_level = FutureVersionValidator.calculate_confidence_score(
                base_trust=v.trust_level,
                prerelease_type=v.prerelease_type,
                has_date=bool(v.release_date),
                source_count=v.confirmation_count
            )
            
        # 7. Sort by version descending
        # (Assuming VersionValidator or simple parse works)
        # We need a robust sort key.
        future_versions.sort(
            key=lambda x: self._version_sort_key(x.version), 
            reverse=True
        )
        
        return future_versions[:5] # Return top 5 candidates

    def _detect_registry(self, name: str) -> Optional[str]:
        # Simple heuristic or reuse logic from VersionDetector
        if name.startswith("@"): return "npm"
        if ":" in name: return "maven"
        # Since we usually know the registry from the Library model, this is just a fallback.
        # Ideally caller provides registry_type.
        return "pypi" 

    def _deduplicate(self, candidates: List[PreReleaseInfo]) -> List[PreReleaseInfo]:
        """Merge duplicates, keeping the most detailed info and boosting trust."""
        version_map: Dict[str, PreReleaseInfo] = {}
        
        for cand in candidates:
            v_str = cand.version
            if v_str not in version_map:
                version_map[v_str] = cand
            else:
                existing = version_map[v_str]
                
                # Boost trust because we found it from another source
                # e.g. If found in Registry (95) and GitHub (95), boost to 99
                # If found in Milestone (85) and GitHub Release (95), take 95 and boost slightly
                
                base_trust = max(existing.trust_level, cand.trust_level)
                boosted_trust = min(100, base_trust + 5)
                
                # Determine which object to keep (the one with higher base trust or published status)
                keep_cand = False
                if cand.is_published and not existing.is_published:
                    keep_cand = True
                elif cand.trust_level > existing.trust_level:
                    keep_cand = True
                elif cand.release_date and not existing.release_date:
                    keep_cand = True
                    
                target = cand if keep_cand else existing
                target.trust_level = boosted_trust
                
                # Merge logic: Ensure we have the best metadata
                if not target.release_date:
                    target.release_date = cand.release_date if keep_cand else existing.release_date
                
                # Merge confirmation counts
                target.confirmation_count = existing.confirmation_count + cand.confirmation_count
                    
                version_map[v_str] = target
                     
        return list(version_map.values())

    def _version_sort_key(self, version: str):
         from packaging.version import parse
         try:
             return parse(version)
         except:
             return version
