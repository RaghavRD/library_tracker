"""
Official package manager registry adapters.

This module provides adapters for fetching version information from
official package registries (PyPI, npm, RubyGems, Cargo, NuGet, Maven)
instead of relying on web search.
"""

from .base import PackageRegistry, VersionInfo, PreReleaseInfo
from .pypi import PyPIRegistry
from .npm import NpmRegistry
from .rubygems import RubyGemsRegistry
from .cargo import CargoRegistry
from .nuget import NuGetRegistry
from .maven import MavenRegistry

__all__ = [
    'PackageRegistry',
    'VersionInfo',
    'PreReleaseInfo',
    'PyPIRegistry',
    'NpmRegistry',
    'RubyGemsRegistry',
    'CargoRegistry',
    'NuGetRegistry',
    'MavenRegistry',
]
