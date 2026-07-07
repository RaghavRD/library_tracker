import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from tracker.models import Project, UpdateCache, FutureUpdateCache, StackComponent

User = get_user_model()

from django.test import Client

@pytest.mark.django_db
class TestDashboardAnalytics:
    def setup_method(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_login(self.user)
        
    def test_projects_page_redirect(self):
        """Test that old dashboard is accessible at new projects url"""
        url = reverse('projects')
        response = self.client.get(url)
        assert response.status_code == 200
        assert "Manage Projects" not in str(response.content) # Allows distinction
        
    def test_analytics_dashboard_loads(self):
        """Test that new dashboard loads and contains analytics data"""
        # Create dummy data
        p = Project.objects.create(
            owner=self.user,
            project_name="Test Project",
            developer_names="Dev",
            developer_emails="test@test.com",
        )
        StackComponent.objects.create(project=p, name="Django", version="5.0", category="Library", key="dependency")
        UpdateCache.objects.create(project=p, library="Django", version="5.1", category="minor")
        FutureUpdateCache.objects.create(library="Django", version="6.0", status="detected", confidence=80)
        
        url = reverse('dashboard')
        response = self.client.get(url)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Check for KPI values and insight sections
        assert "Projects" in content
        assert "Health Score" in content
        assert "Vulnerabilities" in content
        assert "Updates" in content
        assert "Future Risk" in content
        assert "Action Needed" in content
        assert "Top Risky Projects" in content
        
        # Check for Chart.js canvas
        assert 'id="riskTrendChart"' in content
        assert 'id="severityChart"' in content
        assert 'id="stackChart"' in content

    def test_navigation_links(self):
        """Test validation of navbar links existence"""
        url = reverse('dashboard')
        response = self.client.get(url)
        content = response.content.decode('utf-8')
        
        if 'dashboard' not in content and 'projects' not in content:
            print("FAILED TO FIND LINKS")
        
        # Verify the key links are present (resolved via {% url %}, prefix-agnostic)
        assert reverse('dashboard') in content
        assert reverse('projects') in content
