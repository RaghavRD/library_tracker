import pytest
from django.test import override_settings
from django.urls import reverse


@pytest.mark.django_db
@override_settings(GITHUB_LOGIN_ENABLED=False)
def test_login_page_shows_disabled_github_button_when_not_configured(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b"Continue with GitHub" in response.content
    assert b"GitHub login needs OAuth credentials." in response.content
    assert b"disabled" in response.content


@pytest.mark.django_db
@override_settings(
    GITHUB_LOGIN_ENABLED=True,
    SOCIALACCOUNT_PROVIDERS={
        "github": {
            "SCOPE": ["read:user", "user:email"],
            "APPS": [{"client_id": "test-id", "secret": "test-secret", "key": ""}],
        }
    },
)
def test_login_page_posts_to_github_allauth_endpoint_when_configured(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b"Continue with GitHub" in response.content
    assert b'/accounts/github/login/?process=login' in response.content


@pytest.mark.django_db
@override_settings(
    GITHUB_LOGIN_ENABLED=True,
    SOCIALACCOUNT_PROVIDERS={
        "github": {
            "SCOPE": ["read:user", "user:email"],
            "APPS": [{"client_id": "test-id", "secret": "test-secret", "key": ""}],
        }
    },
)
def test_register_page_posts_to_github_allauth_signup_endpoint_when_configured(client):
    response = client.get(reverse("register"))

    assert response.status_code == 200
    assert b"Continue with GitHub" in response.content
    assert b'/accounts/github/login/?process=signup' in response.content
