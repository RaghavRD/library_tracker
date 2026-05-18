"""
Utility for validating and classifying future/pre-release versions.
"""

from packaging.version import parse as parse_version, Version
import re

class FutureVersionValidator:
    """Helper to classify and score future versions."""
    
    # Prerelease type priority (for deciding which is "more stable")
    # Higher value = more likely to be the next stable release
    STABILITY_SCORES = {
        'rc': 90,
        'beta': 70, 
        'alpha': 50,
        'canary': 40,
        'next': 40,
        'dev': 30,
        'milestone': 60, # Milestones are plans, not releases, but high intent
        'roadmap': 20,   # Roadmaps can be vague
    }
    
    @staticmethod
    def classify_prerelease_type(version_str: str) -> str:
        """
        Determine the type of pre-release (alpha, beta, rc, etc.)
        from a version string.
        """
        if not version_str:
            return "unknown"
            
        # 1. Parse using packaging.version (PEP 440 awareness)
        try:
            v = parse_version(version_str)
            if v.pre:
                phase, num = v.pre
                if phase == 'a': return 'alpha'
                if phase == 'b': return 'beta'
                if phase == 'rc': return 'rc'
            if v.is_devrelease:
                return 'dev'
        except:
            pass
            
        # 2. Heuristic fallback for non-PEP 440 (e.g. npm tags)
        lower = version_str.lower()
        if 'rc' in lower: return 'rc'
        if 'beta' in lower: return 'beta'
        if 'alpha' in lower: return 'alpha'
        if 'canary' in lower: return 'canary'
        if 'experimental' in lower: return 'dev'
        if 'nightly' in lower: return 'dev'
        if 'next' in lower: return 'alpha' # 'next' usually means alpha/beta
        
        return "unknown"

    @staticmethod
    def calculate_confidence_score(
        base_trust: int, 
        prerelease_type: str,
        has_date: bool = False,
        source_count: int = 1
    ) -> int:
        """
        Calculate a confidence score (0-100) for a detected future version.
        
        Args:
            base_trust: Trust level of the source (e.g., Registry=95, Blog=75)
            prerelease_type: alpha, beta, rc, etc.
            has_date: Whether a specific release date is known
            source_count: Number of independent sources confirming this
        """
        score = base_trust
        
        # Boost for stability (RC is more "confident" than Alpha)
        # We only add a small boost because 'trust' is about the *source*,
        # but 'confidence' also includes likelihood of actually shipping.
        
        if prerelease_type == 'rc':
            score += 5
        elif prerelease_type == 'beta':
            score += 3
            
        if has_date:
            score += 10
            
        if source_count > 1:
            score += (source_count - 1) * 5
            
        return min(100, score)
