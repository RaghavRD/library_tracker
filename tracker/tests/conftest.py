"""
Pytest configuration and shared fixtures for LibTrack AI tests.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from django.contrib.auth.models import User


@pytest.fixture
def db_setup(db):
    """Ensures database is available for tests."""
    return db


@pytest.fixture
def mock_project(db):
    """Factory fixture for creating test projects."""
    from tracker.models import Project
    
    def _create_project(
        project_name="Test Project",
        developer_names="Test Developer",
        developer_emails="test@example.com",
        notification_type="major, minor, future"
    ):
        return Project.objects.create(
            project_name=project_name,
            developer_names=developer_names,
            developer_emails=developer_emails,
            notification_type=notification_type
        )
    
    return _create_project


@pytest.fixture
def mock_stack_component(db):
    """Factory fixture for creating stack components."""
    from tracker.models import StackComponent
    
    def _create_component(
        project,
        category="library",
        key="library",
        name="numpy",
        version="1.24.0",
        scope=""
    ):
        return StackComponent.objects.create(
            project=project,
            category=category,
            key=key,
            name=name,
            version=version,
            scope=scope
        )
    
    return _create_component


@pytest.fixture
def mock_serper_response():
    """Returns a function to generate mock Serper API responses."""
    
    def _generate_response(library_name, version, is_future=False, confidence=85):
        if is_future:
            return {
                "organic": [
                    {
                        "title": f"{library_name} {version} Roadmap - Planned Release",
                        "link": f"https://{library_name.lower()}.org/roadmap",
                        "snippet": f"Planned release of {library_name} {version} with new features. Expected Q1 2024."
                    },
                    {
                        "title": f"{library_name} Future Plans",
                        "link": f"https://github.com/{library_name.lower()}/issues/123",
                        "snippet": f"Version {version} is in development with breaking changes."
                    }
                ]
            }
        else:
            return {
                "organic": [
                    {
                        "title": f"{library_name} {version} Released",
                        "link": f"https://{library_name.lower()}.org/releases/{version}",
                        "snippet": f"{library_name} {version} has been officially released with bug fixes and improvements."
                    },
                    {
                        "title": f"What's new in {library_name} {version}",
                        "link": f"https://{library_name.lower()}.org/whatsnew",
                        "snippet": f"Major updates in version {version} including performance improvements."
                    }
                ]
            }
    
    return _generate_response


@pytest.fixture
def mock_groq_analysis():
    """Returns a function to generate mock Groq analyzer responses."""
    
    def _generate_analysis(
        library_name,
        version,
        category="major",
        is_released=True,
        confidence=85,
        expected_date=None
    ):
        base_analysis = {
            "library": library_name,
            "version": version,
            "category": category,
            "is_released": is_released,
            "confidence": confidence,
            "release_date": datetime.now().strftime("%Y-%m-%d") if is_released else "",
            "expected_date": expected_date or "",
            "summary": f"{'Upcoming' if not is_released else 'Released'} version {version} with improvements.",
            "source": f"https://{library_name.lower()}.org/releases"
        }
        
        return base_analysis
    
    return _generate_analysis


@pytest.fixture
def mock_mailtrap_success():
    """Mock successful Mailtrap email sending."""
    with patch('tracker.utils.send_mail.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Email sent successfully"
        mock_post.return_value = mock_response
        yield mock_post


@pytest.fixture
def test_user(db):
    """Create a test user for authentication tests."""
    return User.objects.create_user(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )


@pytest.fixture
def future_update_data():
    """Provides sample data for future update scenarios."""
    return {
        "library": "pandas",
        "version": "3.0.0",
        "confidence": 85,
        "expected_date": (datetime.now() + timedelta(days=90)).date(),
        "features": "Major rewrite with improved performance and new data types.",
        "source": "https://pandas.pydata.org/roadmap",
        "status": "detected"
    }


@pytest.fixture
def released_update_data():
    """Provides sample data for released update scenarios."""
    return {
        "library": "numpy",
        "version": "2.0.0",
        "category": "major",
        "release_date": datetime.now().strftime("%Y-%m-%d"),
        "summary": "Major release with breaking changes and performance improvements.",
        "source": "https://numpy.org/releases/2.0.0"
    }
