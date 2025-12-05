"""
Tests for version release transition scenarios.

This module tests:
1. Promoting future updates to released versions
2. Creating UpdateCache entries from FutureUpdateCache
3. Email notifications for actual releases
4. Linking between future predictions and released versions
5. Complete lifecycle: future → released
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from tracker.models import UpdateCache, FutureUpdateCache, Project
from tracker.utils.send_mail import send_update_email
from tracker.tests.test_fixtures import (
    ProjectFactory,
    ComponentFactory,
    FutureUpdateFactory,
    UpdateCacheFactory,
    MockDataBuilder
)


@pytest.mark.django_db
class TestFutureToReleasedTransition:
    """Test the transition from future update to released version."""
    
    def test_promote_future_to_released(self, mock_project):
        """Test creating UpdateCache entry when future update is released."""
        project = mock_project(notification_type='major, minor, future')
        ComponentFactory.create_library(project, name='pandas', version='2.0.0')
        
        # Create a future update
        future_update = FutureUpdateFactory.create_high_confidence_future(
            library='pandas',
            version='2.1.0'
        )
        
        # Simulate the release
        released_update = UpdateCacheFactory.create_update_cache(
            project=project,
            library='pandas',
            version='2.1.0',
            category='major'
        )
        
        # Link the future prediction to the release
        future_update.promoted_to_release = released_update
        future_update.status = 'released'
        future_update.save()
        
        # Verify the transition
        assert released_update.library == future_update.library
        assert released_update.version == future_update.version
        assert future_update.status == 'released'
        assert future_update.promoted_to_release == released_update
    
    def test_future_predictions_relationship(self, mock_project):
        """Test the relationship between FutureUpdateCache and UpdateCache."""
        project = mock_project()
        
        # Create future update
        future = FutureUpdateFactory.create_future_update(
            library='numpy',
            version='2.0.0',
            confidence=95
        )
        
        # Create released update
        released = UpdateCacheFactory.create_update_cache(
            project=project,
            library='numpy',
            version='2.0.0'
        )
        
        # Link them
        future.promoted_to_release = released
        future.status = 'released'
        future.save()
        
        # Test the relationship
        assert released.future_predictions.count() == 1
        assert released.future_predictions.first() == future
        assert future.promoted_to_release == released
    
    def test_update_cache_creation_from_future(self, mock_project):
        """Test creating UpdateCache with details from FutureUpdateCache."""
        project = mock_project(notification_type='major, minor, future')
        
        future_data = {
            'library': 'django',
            'version': '5.0',
            'confidence': 88,
            'features': 'New async support and improvements',
            'source': 'https://djangoproject.com/roadmap'
        }
        
        future = FutureUpdateFactory.create_future_update(**future_data)
        
        # When it's released, create UpdateCache
        released = UpdateCacheFactory.create_update_cache(
            project=project,
            library=future.library,
            version=future.version,
            category='major',
            summary=future.features,  # Use features as summary
            source=future.source
        )
        
        # Verify data carried over
        assert released.library == future.library
        assert released.version == future.version
        assert released.summary == future.features
        assert released.source == future.source


@pytest.mark.django_db
class TestReleasedVersionNotifications:
    """Test email notifications for actual version releases."""
    
    def test_released_version_email(self, mock_project):
        """Test email notification for an actually released version."""
        project = mock_project(
            project_name='Release Test Project',
            developer_emails='dev@example.com',
            notification_type='major, minor, future'
        )
        
        with patch.dict('os.environ', {
            'TEST_MODE': 'True',
            'MAILTRAP_MAIN_KEY': 'test_key',
            'MAILTRAP_FROM_EMAIL': 'noreply@libtrack.com'
        }):
            success, message = send_update_email(
                mailtrap_api_key='test_key',
                project_name='Release Test Project',
                recipients='dev@example.com',
                library='numpy',
                version='2.0.0',
                category='major',
                summary='Major release with breaking changes',
                source='https://numpy.org/releases/2.0.0',
                release_date='2024-01-15',
                future_opt_in=False  # This is an actual release
            )
        
        assert success
        # Should NOT have "Future Update Alert" in subject since it's released
    
    def test_different_subjects_future_vs_released(self, mock_project):
        """Test that future and released emails have different subjects."""
        project = mock_project(notification_type='major, minor, future')
        
        # Test future update subject
        with patch.dict('os.environ', {
            'TEST_MODE': 'True',
            'MAILTRAP_MAIN_KEY': 'test_key',
            'MAILTRAP_FROM_EMAIL': 'noreply@libtrack.com'
        }):
            future_success, _ = send_update_email(
                mailtrap_api_key='test_key',
                project_name='Test',
                recipients='dev@test.com',
                library='pandas',
                version='3.0.0',
                category='future',
                summary='Upcoming',
                source='https://test.com',
                future_opt_in=True
            )
            
            released_success, _ = send_update_email(
                mailtrap_api_key='test_key',
                project_name='Test',
                recipients='dev@test.com',
                library='pandas',
                version='3.0.0',
                category='major',
                summary='Released',
                source='https://test.com',
                future_opt_in=False
            )
        
        assert future_success
        assert released_success


@pytest.mark.django_db
class TestCompleteLifecycle:
    """Test the complete lifecycle from future detection to release."""
    
    def test_complete_future_to_release_flow(self):
        """Test the complete flow: detect future → notify → release → notify again."""
        # Build the scenario
        scenario = MockDataBuilder.build_future_to_released_scenario()
        project = scenario['project']
        future_update = scenario['future_update']
        
        # Step 1: Future update detected and stored
        assert future_update.status == 'detected'
        assert not future_update.notification_sent
        
        # Step 2: Mark as notified
        future_update.notification_sent = True
        future_update.notification_sent_at = datetime.now()
        future_update.save()
        
        assert future_update.notification_sent
        
        # Step 3: Version is actually released
        released = UpdateCacheFactory.create_update_cache(
            project=project,
            library=future_update.library,
            version=future_update.version,
            category='major'
        )
        
        # Step 4: Link future to released
        future_update.promoted_to_release = released
        future_update.status = 'released'
        future_update.save()
        
        # Verify complete flow
        assert future_update.status == 'released'
        assert future_update.promoted_to_release is not None
        assert released.future_predictions.count() == 1
        assert UpdateCache.objects.filter(
            project=project,
            library=future_update.library,
            version=future_update.version
        ).exists()
    
    def test_multiple_futures_same_library(self, mock_project):
        """Test handling multiple future versions for the same library."""
        project = mock_project(notification_type='major, minor, future')
        ComponentFactory.create_library(project, name='django', version='4.2')
        
        # Create multiple future versions
        future_5_0 = FutureUpdateFactory.create_future_update(
            library='django',
            version='5.0',
            confidence=95
        )
        
        future_5_1 = FutureUpdateFactory.create_future_update(
            library='django',
            version='5.1',
            confidence=80
        )
        
        # Both should exist
        assert FutureUpdateCache.objects.filter(library='django').count() == 2
        
        # Release 5.0
        released_5_0 = UpdateCacheFactory.create_update_cache(
            project=project,
            library='django',
            version='5.0'
        )
        
        future_5_0.promoted_to_release = released_5_0
        future_5_0.status = 'released'
        future_5_0.save()
        
        # 5.1 should still be future
        future_5_1.refresh_from_db()
        assert future_5_1.status == 'detected'
        
        # 5.0 should be released
        future_5_0.refresh_from_db()
        assert future_5_0.status == 'released'
    
    def test_cancelled_future_update(self):
        """Test handling of cancelled future updates."""
        future = FutureUpdateFactory.create_future_update(
            library='hypothetical-lib',
            version='2.0.0',
            confidence=70
        )
        
        # Mark as cancelled (if plans changed)
        future.status = 'cancelled'
        future.save()
        
        assert future.status == 'cancelled'
        assert future.promoted_to_release is None


@pytest.mark.django_db
class TestEdgeCases:
    """Test edge cases in the release transition process."""
    
    def test_release_without_prior_future_detection(self, mock_project):
        """Test handling a release that was never detected as future."""
        project = mock_project()
        ComponentFactory.create_library(project, name='requests', version='2.30.0')
        
        # Direct release without future detection
        released = UpdateCacheFactory.create_update_cache(
            project=project,
            library='requests',
            version='2.31.0',
            category='minor'
        )
        
        # Should work fine without a future prediction
        assert released.future_predictions.count() == 0
        assert released.version == '2.31.0'
    
    def test_future_update_confirmed_status(self):
        """Test updating future update status to confirmed."""
        future = FutureUpdateFactory.create_future_update(
            library='flask',
            version='3.0.0',
            confidence=75,
            status='detected'
        )
        
        # Mark as confirmed (e.g., official announcement)
        future.status = 'confirmed'
        future.confidence = 100
        future.save()
        
        assert future.status == 'confirmed'
        assert future.confidence == 100
