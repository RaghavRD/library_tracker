import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tracker.services.github_account_service import GitHubAccountService
from tracker.services.github_repo_import_service import GitHubRepoImportService


User = get_user_model()


def _github_response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def _encoded_content(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_parse_github_repo_url():
    assert GitHubRepoImportService.parse_repo_url("https://github.com/openai/codex") == ("openai", "codex")
    assert GitHubRepoImportService.parse_repo_url("github.com/openai/codex.git") == ("openai", "codex")
    assert GitHubRepoImportService.parse_repo_url("https://example.com/openai/codex") is None


def test_import_repository_reads_supported_root_manifests():
    package_json = json.dumps({"dependencies": {"react": "^18.2.0"}})
    requirements_txt = "Django==5.2.1\n"

    def fake_get(url, headers=None, timeout=None, params=None):
        if url.endswith("/contributors"):
            return _github_response(payload=[{"login": "octocat", "type": "User"}])
        if url.endswith("/repos/acme/app"):
            return _github_response(payload={"default_branch": "main"})
        if "contents/package.json" in url:
            return _github_response(payload={"encoding": "base64", "content": _encoded_content(package_json)})
        if "contents/requirements.txt" in url:
            return _github_response(payload={"encoding": "base64", "content": _encoded_content(requirements_txt)})
        return _github_response(status_code=404)

    with patch("tracker.services.github_repo_import_service.requests.get", side_effect=fake_get):
        result = GitHubRepoImportService().import_repository("https://github.com/acme/app")

    assert result["error"] == ""
    assert result["repository"] == "acme/app"
    assert result["files"] == ["package.json", "requirements.txt"]
    assert [(item["name"], item["version"], item["scope"]) for item in result["components"]] == [
        ("react", "18.2.0", "npm/runtime"),
        ("Django", "5.2.1", "pypi/pinned"),
    ]


def test_import_repository_prefers_lockfile_versions():
    package_lock = json.dumps({"packages": {"node_modules/react": {"version": "18.2.0"}}})
    package_json = json.dumps({"dependencies": {"react": "^18.0.0", "vite": "^5.1.4"}})

    def fake_get(url, headers=None, timeout=None, params=None):
        if url.endswith("/contributors"):
            return _github_response(payload=[{"login": "octocat", "type": "User"}])
        if url.endswith("/repos/acme/app"):
            return _github_response(payload={"default_branch": "main"})
        if "contents/package-lock.json" in url:
            return _github_response(payload={"encoding": "base64", "content": _encoded_content(package_lock)})
        if "contents/package.json" in url:
            return _github_response(payload={"encoding": "base64", "content": _encoded_content(package_json)})
        return _github_response(status_code=404)

    with patch("tracker.services.github_repo_import_service.requests.get", side_effect=fake_get):
        result = GitHubRepoImportService().import_repository("https://github.com/acme/app")

    assert result["error"] == ""
    assert result["files"] == ["package-lock.json", "package.json"]
    assert [(item["name"], item["version"], item["scope"]) for item in result["components"]] == [
        ("react", "18.2.0", "npm/lockfile"),
        ("vite", "5.1.4", "npm/runtime"),
    ]


def test_import_repository_reports_invalid_url():
    result = GitHubRepoImportService().import_repository("https://example.com/acme/app")

    assert result["components"] == []
    assert "valid GitHub" in result["error"]


@pytest.mark.django_db
def test_import_github_repo_endpoint_requires_login(client):
    response = client.post(reverse("import_github_repo"), {"repo_id": "123"})

    assert response.status_code == 302


@pytest.mark.django_db
def test_import_github_repo_endpoint_returns_components(client):
    user = User.objects.create_user(username="github-user", password="pass12345")
    client.force_login(user)

    with patch.object(
        GitHubAccountService,
        "get_repository_for_user",
        return_value={
            "repository": {
                "id": 123,
                "html_url": "https://github.com/acme/app",
                "full_name": "acme/app",
            },
            "error": "",
        },
    ), patch.object(
        GitHubAccountService,
        "get_access_token",
        return_value="github-token",
    ), patch.object(
        GitHubRepoImportService,
        "import_repository",
        return_value={
            "components": [{"name": "react", "version": "18.2.0"}],
            "warnings": [],
            "files": ["package.json"],
            "repository": "acme/app",
            "default_branch": "main",
            "error": "",
        },
    ):
        response = client.post(reverse("import_github_repo"), {"repo_id": "123"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["repository"] == "acme/app"
    assert payload["components"][0]["name"] == "react"


@pytest.mark.django_db
def test_github_repositories_endpoint_returns_connected_repositories(client):
    user = User.objects.create_user(username="repo-user", password="pass12345")
    client.force_login(user)

    with patch.object(
        GitHubAccountService,
        "list_repositories",
        return_value={
            "repositories": [
                {
                    "id": 11,
                    "name": "public-repo",
                    "full_name": "acme/public-repo",
                    "html_url": "https://github.com/acme/public-repo",
                    "private": False,
                    "fork": False,
                    "archived": False,
                    "default_branch": "main",
                    "description": "",
                    "updated_at": "2026-07-31T00:00:00Z",
                },
                {
                    "id": 12,
                    "name": "private-repo",
                    "full_name": "acme/private-repo",
                    "html_url": "https://github.com/acme/private-repo",
                    "private": True,
                    "fork": False,
                    "archived": False,
                    "default_branch": "main",
                    "description": "",
                    "updated_at": "2026-07-31T00:00:00Z",
                },
            ],
            "error": "",
        },
    ):
        response = client.get(reverse("github_repositories"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["repositories"]) == 2
    assert payload["repositories"][1]["private"] is True


@pytest.mark.django_db
def test_import_github_repo_endpoint_rejects_unlinked_repository(client):
    user = User.objects.create_user(username="github-user-2", password="pass12345")
    client.force_login(user)

    with patch.object(
        GitHubAccountService,
        "get_repository_for_user",
        return_value={
            "repository": None,
            "error": "Select a repository from your connected GitHub account.",
        },
    ):
        response = client.post(reverse("import_github_repo"), {"repo_id": "999"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert "connected GitHub account" in payload["error"]
