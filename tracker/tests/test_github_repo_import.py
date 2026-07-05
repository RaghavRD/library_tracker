import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

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

    def fake_get(url, headers=None, timeout=None):
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


def test_import_repository_reports_invalid_url():
    result = GitHubRepoImportService().import_repository("https://example.com/acme/app")

    assert result["components"] == []
    assert "valid GitHub" in result["error"]


@pytest.mark.django_db
def test_import_github_repo_endpoint_requires_login(client):
    response = client.post(reverse("import_github_repo"), {"repo_url": "https://github.com/acme/app"})

    assert response.status_code == 302


@pytest.mark.django_db
def test_import_github_repo_endpoint_returns_components(client):
    user = User.objects.create_user(username="github-user", password="pass12345")
    client.force_login(user)

    with patch.object(
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
        response = client.post(reverse("import_github_repo"), {"repo_url": "https://github.com/acme/app"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["repository"] == "acme/app"
    assert payload["components"][0]["name"] == "react"
