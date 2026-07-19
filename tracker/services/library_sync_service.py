"""
LibrarySyncService: Synchronizes StackComponents with central Library records.

Purpose:
  Ensures all project components are linked to a canonical Library entity.
  This avoids redundant API calls when multiple projects track the same library.

Workflow:
  1. Find all unlinked StackComponents
  2. For each component, create or link to a Library record
  3. Infer component type (library, language, tool) and registry type
"""

import logging
from tracker.models import StackComponent, Library

logger = logging.getLogger(__name__)


class LibrarySyncService:
    """
    Synchronizes project components with the central Library model.
    Ensures single source of truth for library metadata.
    """

    def __init__(self):
        """Initialize the sync service."""
        self.synced_count = 0
        self.created_count = 0

    def sync_all_libraries(self, stdout_writer=None, owner=None):
        """
        Link all unlinked StackComponents to Library records.

        Args:
            stdout_writer: Optional callable to write status updates (e.g., self.stdout.write)

        Returns:
            dict: Summary with 'synced_count' and 'created_count'
        """
        self._log(stdout_writer, "Starting library sync...")

        # Find components not yet linked to a Library
        unlinked_components = StackComponent.objects.filter(library_ref__isnull=True)
        if owner is not None:
            unlinked_components = unlinked_components.filter(project__owner=owner)
        count = unlinked_components.count()
        self._log(stdout_writer, f"Found {count} unlinked components.")

        for component in unlinked_components:
            self._sync_component(component, stdout_writer)

        self._log(
            stdout_writer,
            f"✅ Sync complete: {self.synced_count} linked, {self.created_count} created.",
        )
        return {"synced_count": self.synced_count, "created_count": self.created_count}

    def _sync_component(self, component: StackComponent, stdout_writer=None):
        """
        Link a single StackComponent to a Library, creating the Library if needed.

        Args:
            component: StackComponent instance to link
            stdout_writer: Optional callable for logging
        """
        # Normalize the component name (lowercase, replace spaces with hyphens)
        raw_name = component.name.strip()
        normalized_key = raw_name.lower().replace(" ", "-")

        # Infer component type (library vs language vs tool)
        component_type = self._infer_component_type(component)

        # Get or create the Library record
        library, created = Library.objects.get_or_create(
            key=normalized_key,
            defaults={
                "name": raw_name,
                "component_type": component_type,
                "registry_type": "",  # Will be inferred later during fetch
            },
        )

        # Link the component to the library
        component.library_ref = library
        component.save()

        self.synced_count += 1
        if created:
            self.created_count += 1
            self._log(
                stdout_writer,
                f"[NEW] Created Library: {library.name} (type: {component_type})",
            )
        else:
            self._log(
                stdout_writer,
                f"[LINKED] {component.name} → {library.name}",
            )

    def _infer_component_type(self, component: StackComponent) -> str:
        """
        Infer whether a component is a library, language, or tool.

        Args:
            component: StackComponent instance

        Returns:
            str: One of 'library', 'language', or 'tool'
        """
        # If explicitly marked as language in the component key
        if component.key and "language" in component.key.lower():
            return "language"

        # Check category field for hints
        category_lower = (component.category or "").lower()
        if "language" in category_lower:
            return "language"
        if "tool" in category_lower:
            return "tool"

        # Default to library
        return "library"

    @staticmethod
    def _log(stdout_writer, message: str):
        """Helper to write log messages if a writer is provided."""
        if stdout_writer:
            stdout_writer(message)
        else:
            logger.info(message)
