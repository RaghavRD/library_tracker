"""
Official package manager registry adapters.

This module provides adapters for fetching version information from
official package registries (PyPI, npm, RubyGems, etc.) instead of
relying on web search.
"""

from .base import PackageRegistry, VersionInfo
from .pypi import PyPIRegistry
from .npm import NpmRegistry

__all__ = [
    'PackageRegistry',
    'VersionInfo',
    'PyPIRegistry',
    'NpmRegistry',
]
