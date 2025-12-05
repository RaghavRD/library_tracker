"""
Mock data factories and utilities for testing.
"""
from datetime import datetime, timedelta
from tracker.models import Project, StackComponent, UpdateCache, FutureUpdateCache


class ProjectFactory:
    """Factory for creating test projects with various configurations."""
    
    @staticmethod
    def create_basic_project(**kwargs):
        """Create a basic project with default settings."""
        defaults = {
            'project_name': 'Test Project',
            'developer_names': 'John Doe, Jane Smith',
            'developer_emails': 'john@example.com, jane@example.com',
            'notification_type': 'major, minor'
        }
        defaults.update(kwargs)
        return Project.objects.create(**defaults)
    
    @staticmethod
    def create_future_enabled_project(**kwargs):
        """Create a project with future update notifications enabled."""
        kwargs['notification_type'] = 'major, minor, future'
        return ProjectFactory.create_basic_project(**kwargs)
    
    @staticmethod
    def create_major_only_project(**kwargs):
        """Create a project that only wants major update notifications."""
        kwargs['notification_type'] = 'major'
        return ProjectFactory.create_basic_project(**kwargs)


class ComponentFactory:
    """Factory for creating stack components."""
    
    @staticmethod
    def create_library(project, name='numpy', version='1.24.0', **kwargs):
        """Create a library component."""
        defaults = {
            'project': project,
            'category': 'library',
            'key': 'library',
            'name': name,
            'version': version,
            'scope': ''
        }
        defaults.update(kwargs)
        return StackComponent.objects.create(**defaults)
    
    @staticmethod
    def create_language(project, name='Python', version='3.11', **kwargs):
        """Create a language component."""
        defaults = {
            'project': project,
            'category': 'language',
            'key': 'language',
            'name': name,
            'version': version,
            'scope': ''
        }
        defaults.update(kwargs)
        return StackComponent.objects.create(**defaults)
    
    @staticmethod
    def create_multiple_libraries(project, libraries):
        """
        Create multiple library components.
        
        Args:
            project: Project instance
            libraries: List of tuples (name, version)
        
        Returns:
            List of created StackComponent instances
        """
        components = []
        for name, version in libraries:
            components.append(
                ComponentFactory.create_library(project, name=name, version=version)
            )
        return components


class FutureUpdateFactory:
    """Factory for creating future update cache entries."""
    
    @staticmethod
    def create_future_update(
        library='pandas',
        version='3.0.0',
        confidence=85,
        days_until_release=90,
        **kwargs
    ):
        """Create a future update entry."""
        defaults = {
            'library': library,
            'version': version,
            'confidence': confidence,
            'expected_date': (datetime.now() + timedelta(days=days_until_release)).date(),
            'features': f'Planned features for {library} {version}',
            'source': f'https://{library.lower()}.org/roadmap',
            'status': 'detected',
            'notification_sent': False
        }
        defaults.update(kwargs)
        return FutureUpdateCache.objects.create(**defaults)
    
    @staticmethod
    def create_high_confidence_future(library='numpy', version='2.1.0', **kwargs):
        """Create a high-confidence future update (90%+)."""
        kwargs['confidence'] = kwargs.get('confidence', 95)
        return FutureUpdateFactory.create_future_update(library, version, **kwargs)
    
    @staticmethod
    def create_low_confidence_future(library='scipy', version='2.0.0', **kwargs):
        """Create a low-confidence future update (below threshold)."""
        kwargs['confidence'] = kwargs.get('confidence', 50)
        return FutureUpdateFactory.create_future_update(library, version, **kwargs)
    
    @staticmethod
    def create_notified_future(library='matplotlib', version='4.0.0', **kwargs):
        """Create a future update that has already been notified."""
        kwargs['notification_sent'] = True
        kwargs['notification_sent_at'] = datetime.now()
        return FutureUpdateFactory.create_future_update(library, version, **kwargs)


class UpdateCacheFactory:
    """Factory for creating update cache entries (released versions)."""
    
    @staticmethod
    def create_update_cache(
        project,
        library='numpy',
        version='2.0.0',
        category='major',
        **kwargs
    ):
        """Create an update cache entry."""
        defaults = {
            'project': project,
            'library': library,
            'version': version,
            'category': category,
            'release_date': datetime.now().strftime("%Y-%m-%d"),
            'summary': f'Release summary for {library} {version}',
            'source': f'https://{library.lower()}.org/releases/{version}'
        }
        defaults.update(kwargs)
        return UpdateCache.objects.create(**defaults)
    
    @staticmethod
    def create_major_release(project, library='django', version='5.0', **kwargs):
        """Create a major release update."""
        kwargs['category'] = 'major'
        return UpdateCacheFactory.create_update_cache(project, library, version, **kwargs)
    
    @staticmethod
    def create_minor_release(project, library='requests', version='2.31.1', **kwargs):
        """Create a minor release update."""
        kwargs['category'] = 'minor'
        return UpdateCacheFactory.create_update_cache(project, library, version, **kwargs)


class MockDataBuilder:
    """Builder for creating complex test scenarios."""
    
    @staticmethod
    def build_complete_project_scenario():
        """
        Build a complete project with components, updates, and future updates.
        
        Returns:
            dict with project, components, updates, and future_updates
        """
        project = ProjectFactory.create_future_enabled_project(
            project_name='Complete Test Project'
        )
        
        # Create components
        components = ComponentFactory.create_multiple_libraries(
            project,
            [
                ('numpy', '1.24.0'),
                ('pandas', '2.0.0'),
                ('django', '4.2')
            ]
        )
        
        # Create some released updates
        updates = [
            UpdateCacheFactory.create_major_release(
                project, library='numpy', version='2.0.0'
            )
        ]
        
        # Create some future updates
        future_updates = [
            FutureUpdateFactory.create_high_confidence_future(
                library='pandas', version='3.0.0'
            ),
            FutureUpdateFactory.create_future_update(
                library='django', version='5.0', confidence=80
            )
        ]
        
        return {
            'project': project,
            'components': components,
            'updates': updates,
            'future_updates': future_updates
        }
    
    @staticmethod
    def build_future_to_released_scenario():
        """
        Build a scenario where a future update transitions to released.
        
        Returns:
            dict with project, future_update, and setup for release
        """
        project = ProjectFactory.create_future_enabled_project(
            project_name='Transition Test Project'
        )
        
        ComponentFactory.create_library(
            project, name='scikit-learn', version='1.3.0'
        )
        
        future_update = FutureUpdateFactory.create_high_confidence_future(
            library='scikit-learn',
            version='1.4.0',
            confidence=90
        )
        
        return {
            'project': project,
            'future_update': future_update,
            'library': 'scikit-learn',
            'future_version': '1.4.0',
            'current_version': '1.3.0'
        }
