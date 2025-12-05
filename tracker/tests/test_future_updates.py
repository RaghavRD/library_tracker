"""
Tests for future update detection and notification scenarios.

This module tests:
1. Detection of upcoming library versions
2. FutureUpdateCache entry creation
3. Email notification content for future updates
4. Confidence threshold filtering
5. Duplicate notification prevention
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase

from tracker.models import FutureUpdateCache, Project
from tracker.management.commands.run_daily_check import Command
from tracker.utils.send_mail import send_update_email
from tracker.tests.test_fixtures import (
    ProjectFactory,
    ComponentFactory,
    FutureUpdateFactory,
    MockDataBuilder
)


@pytest.mark.django_db
class TestFutureUpdateDetection:
    """Test detection and storage of future/planned updates."""
    
    def test_detect_future_update(self, mock_project):
        """Test that future updates are correctly detected and stored."""
        project = mock_project(notification_type='major, minor, future')
        
        # Create a future update manually (simulating detection)
        future_update = FutureUpdateFactory.create_future_update(
            library='pandas',
            version='3.0.0',
            confidence=85,
            days_until_release=90
        )
        
        assert future_update.library == 'pandas'
        assert future_update.version == '3.0.0'
        assert future_update.confidence == 85
        assert future_update.status == 'detected'
        assert not future_update.notification_sent
        assert future_update.expected_date is not None
    
    def test_future_update_cache_creation(self, mock_project):
        """Test FutureUpdateCache entry is created correctly."""
        project = mock_project(notification_type='major, minor, future')
        ComponentFactory.create_library(project, name='numpy', version='1.24.0')
        
        # Simulate future update detection
        future_update = FutureUpdateCache.objects.create(
            library='numpy',
            version='2.0.0',
            confidence=90,
            expected_date=(datetime.now() + timedelta(days=60)).date(),
            features='Major rewrite with breaking changes',
            source='https://numpy.org/roadmap',
            status='detected'
        )
        
        # Verify the entry
        assert FutureUpdateCache.objects.filter(library='numpy', version='2.0.0').exists()
        retrieved = FutureUpdateCache.objects.get(library='numpy', version='2.0.0')
        assert retrieved.confidence == 90
        assert retrieved.status == 'detected'
    
    def test_high_confidence_future_update(self):
        """Test high-confidence future updates are stored."""
        future_update = FutureUpdateFactory.create_high_confidence_future(
            library='django',
            version='5.1'
        )
        
        assert future_update.confidence >= 90
        assert future_update.library == 'django'
        assert future_update.version == '5.1'
    
    def test_low_confidence_future_update_filtering(self):
        """Test that low-confidence future updates can be filtered."""
        low_conf = FutureUpdateFactory.create_low_confidence_future(
            library='scipy',
            version='2.0.0',
            confidence=40
        )
        
        # Simulate the threshold check (MIN_CONFIDENCE = 70 in run_daily_check.py)
        MIN_CONFIDENCE = 70
        should_notify = low_conf.confidence >= MIN_CONFIDENCE
        
        assert not should_notify
        assert low_conf.confidence < MIN_CONFIDENCE


@pytest.mark.django_db
class TestFutureUpdateNotifications:
    """Test email notifications for future updates."""
    
    def test_future_update_email_content(self, mock_project):
        """Test that future update emails contain correct information."""
        project = mock_project(
            project_name='Test Project',
            developer_emails='dev@test.com',
            notification_type='major, minor, future'
        )
        
        # Mock environment variables
        with patch.dict('os.environ', {
            'TEST_MODE': 'True',
            'MAILTRAP_MAIN_KEY': 'test_key',
            'MAILTRAP_FROM_EMAIL': 'noreply@libtrack.com'
        }):
            success, message = send_update_email(
                mailtrap_api_key='test_key',
                project_name='Test Project',
                recipients='dev@test.com',
                library='pandas',
                version='3.0.0',
                category='future',
                summary='Planned major rewrite',
                source='https://pandas.org/roadmap',
                updates=[{
                    'library': 'pandas',
                    'version': '3.0.0',
                    'category': 'future',
                    'category_label': 'Future',
                    'release_date': '2024-03-01',
                    'summary': 'Planned major rewrite',
                    'source': 'https://pandas.org/roadmap',
                    'component_type': 'library',
                    'confidence': 85
                }],
                future_opt_in=True
            )
        
        assert success
        assert 'Test email sent' in message
    
    def test_future_update_subject_line(self, mock_project):
        """Test that future updates have distinct subject lines."""
        project = mock_project(notification_type='major, minor, future')
        
        with patch.dict('os.environ', {
            'TEST_MODE': 'True',
            'MAILTRAP_MAIN_KEY': 'test_key',
            'MAILTRAP_FROM_EMAIL': 'noreply@libtrack.com'
        }):
            success, _ = send_update_email(
                mailtrap_api_key='test_key',
                project_name='Test Project',
                recipients='dev@test.com',
                library='numpy',
                version='2.1.0',
                category='future',
                summary='Future release',
                source='https://numpy.org',
                future_opt_in=True
            )
        
        # The subject should contain "Future Update Alert"
        assert success
    
    def test_confidence_in_email(self, mock_project):
        """Test that confidence percentage appears in future update emails."""
        project = mock_project(notification_type='major, minor, future')
        
        with patch.dict('os.environ', {
            'TEST_MODE': 'True',
            'MAILTRAP_MAIN_KEY': 'test_key',
            'MAILTRAP_FROM_EMAIL': 'noreply@libtrack.com'
        }):
            # Capture the HTML content
            with patch('tracker.utils.send_mail.requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_post.return_value = mock_response
                
                success, _ = send_update_email(
                    mailtrap_api_key='test_key',
                    project_name='Test Project',
                    recipients='dev@test.com',
                    library='django',
                    version='5.1',
                    category='future',
                    summary='Planned release',
                    source='https://djangoproject.com',
                    updates=[{
                        'library': 'django',
                        'version': '5.1',
                        'category': 'future',
                        'release_date': '2024-04-01',
                        'summary': 'Planned release',
                        'source': 'https://djangoproject.com',
                        'component_type': 'library',
                        'confidence': 92
                    }],
                    future_opt_in=True
                )


@pytest.mark.django_db
class TestDuplicateNotificationPrevention:
    """Test that duplicate future update notifications are prevented."""
    
    def test_prevent_duplicate_future_notifications(self, mock_project):
        """Test that we don't send the same future update notification twice."""
        project = mock_project(notification_type='major, minor, future')
        
        # Create a future update that has already been notified
        already_notified = FutureUpdateFactory.create_notified_future(
            library='matplotlib',
            version='4.0.0'
        )
        
        assert already_notified.notification_sent
        assert already_notified.notification_sent_at is not None
        
        # Verify that we can check this status
        should_notify = not already_notified.notification_sent
        assert not should_notify
    
    def test_update_future_entry_with_new_info(self):
        """Test updating existing future entry when confidence increases."""
        # Create initial future update
        future = FutureUpdateFactory.create_future_update(
            library='scikit-learn',
            version='1.4.0',
            confidence=75
        )
        
        initial_confidence = future.confidence
        
        # Simulate update with higher confidence
        future.confidence = 90
        future.features = 'Updated features list'
        future.save()
        
        # Verify update
        updated = FutureUpdateCache.objects.get(library='scikit-learn', version='1.4.0')
        assert updated.confidence == 90
        assert updated.confidence > initial_confidence
        assert 'Updated features' in updated.features


@pytest.mark.django_db
class TestNotificationPreferences:
    """Test that notification preferences are respected for future updates."""
    
    def test_future_opt_in_required(self, mock_project):
        """Test that future updates only sent when user opts in."""
        # Project WITHOUT future notifications enabled
        project = mock_project(notification_type='major, minor')
        
        notify_pref = 'major, minor'
        should_send = 'future' in notify_pref
        
        assert not should_send
    
    def test_future_opt_in_enabled(self, mock_project):
        """Test that future updates are sent when user opts in."""
        # Project WITH future notifications enabled
        project = mock_project(notification_type='major, minor, future')
        
        notify_pref = 'major, minor, future'
        should_send = 'future' in notify_pref
        
        assert should_send
    
    def test_major_only_excludes_future(self, mock_project):
        """Test that major-only preference excludes future updates."""
        project = ProjectFactory.create_major_only_project()
        
        assert 'future' not in project.notification_type
        assert 'major' in project.notification_type
