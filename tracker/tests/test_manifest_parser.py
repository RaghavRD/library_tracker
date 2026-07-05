import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tracker.services.manifest_parser_service import ManifestParserService


User = get_user_model()


def test_parse_package_json_dependencies():
    content = json.dumps(
        {
            "dependencies": {
                "react": "^18.2.0",
                "@reduxjs/toolkit": "~2.2.1",
            },
            "devDependencies": {
                "vite": "5.1.4",
                "local-tool": "file:../local-tool",
            },
        }
    )

    result = ManifestParserService.parse("package_json", content)

    assert result["error"] == ""
    assert result["components"] == [
        {
            "category": "Package",
            "key": "library",
            "name": "react",
            "version": "18.2.0",
            "scope": "npm/runtime",
        },
        {
            "category": "Package",
            "key": "library",
            "name": "@reduxjs/toolkit",
            "version": "2.2.1",
            "scope": "npm/runtime",
        },
        {
            "category": "Package",
            "key": "library",
            "name": "vite",
            "version": "5.1.4",
            "scope": "npm/development",
        },
    ]
    assert any("local-tool" in warning for warning in result["warnings"])


def test_parse_requirements_txt_pinned_dependencies():
    content = """
    Django==5.2.1
    requests>=2.31.0
    # comment
    -r base.txt
    unpinned-package
    uvicorn[standard]==0.30.0 ; python_version >= "3.11"
    """

    result = ManifestParserService.parse("requirements_txt", content)

    assert result["error"] == ""
    assert result["components"] == [
        {
            "category": "Package",
            "key": "library",
            "name": "Django",
            "version": "5.2.1",
            "scope": "pypi/pinned",
        },
        {
            "category": "Package",
            "key": "library",
            "name": "requests",
            "version": "2.31.0",
            "scope": "pypi/>=",
        },
        {
            "category": "Package",
            "key": "library",
            "name": "uvicorn",
            "version": "0.30.0",
            "scope": "pypi/pinned",
        },
    ]
    assert any("unpinned" in warning or "unsupported" in warning for warning in result["warnings"])


def test_parse_manifest_reports_invalid_package_json():
    result = ManifestParserService.parse("package_json", "{bad json")

    assert result["components"] == []
    assert "Invalid package.json" in result["error"]


@pytest.mark.django_db
def test_parse_manifest_endpoint_requires_login(client):
    response = client.post(
        reverse("parse_manifest"),
        {"manifest_type": "requirements_txt", "manifest_content": "Django==5.2.1"},
    )

    assert response.status_code == 302


@pytest.mark.django_db
def test_parse_manifest_endpoint_returns_components(client):
    user = User.objects.create_user(username="manifest-user", password="pass12345")
    client.force_login(user)

    response = client.post(
        reverse("parse_manifest"),
        {"manifest_type": "requirements_txt", "manifest_content": "Django==5.2.1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["components"][0]["name"] == "Django"
    assert payload["components"][0]["version"] == "5.2.1"
