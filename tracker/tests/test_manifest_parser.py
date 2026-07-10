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


def test_parse_node_lockfiles():
    package_lock = json.dumps(
        {
            "packages": {
                "": {"name": "app"},
                "node_modules/react": {"version": "18.2.0"},
                "node_modules/@reduxjs/toolkit": {"version": "2.2.1"},
            }
        }
    )
    yarn_lock = """
    react@^18.0.0:
      version "18.2.0"
    "@reduxjs/toolkit@^2.0.0":
      version "2.2.1"
    """
    pnpm_lock = """
    packages:
      /react@18.2.0:
        resolution: {integrity: sha512-test}
      /@reduxjs/toolkit@2.2.1:
        resolution: {integrity: sha512-test}
    """

    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("package_lock_json", package_lock)["components"]] == [
        ("react", "18.2.0", "npm/lockfile"),
        ("@reduxjs/toolkit", "2.2.1", "npm/lockfile"),
    ]
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("yarn_lock", yarn_lock)["components"]] == [
        ("react", "18.2.0", "npm/yarn-lock"),
        ("@reduxjs/toolkit", "2.2.1", "npm/yarn-lock"),
    ]
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("pnpm_lock", pnpm_lock)["components"]] == [
        ("react", "18.2.0", "npm/pnpm-lock"),
        ("@reduxjs/toolkit", "2.2.1", "npm/pnpm-lock"),
    ]


def test_parse_python_project_and_lockfiles():
    pyproject = """
    [project]
    dependencies = ["Django>=5.2.1", "requests==2.31.0"]

    [tool.poetry.dependencies]
    python = "^3.11"
    fastapi = "^0.110.0"

    [tool.poetry.group.dev.dependencies]
    pytest = "^8.3.0"
    """
    poetry_lock = """
    [[package]]
    name = "django"
    version = "5.2.1"

    [[package]]
    name = "requests"
    version = "2.31.0"
    """
    pipfile_lock = json.dumps(
        {
            "default": {"django": {"version": "==5.2.1"}},
            "develop": {"pytest": {"version": "==8.3.4"}},
        }
    )

    assert [(item["name"], item["version"]) for item in ManifestParserService.parse("pyproject_toml", pyproject)["components"]] == [
        ("Django", "5.2.1"),
        ("requests", "2.31.0"),
        ("fastapi", "0.110.0"),
        ("pytest", "8.3.0"),
    ]
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("poetry_lock", poetry_lock)["components"]] == [
        ("django", "5.2.1", "pypi/poetry-lock"),
        ("requests", "2.31.0", "pypi/poetry-lock"),
    ]
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("pipfile_lock", pipfile_lock)["components"]] == [
        ("django", "5.2.1", "pypi/pipfile-lock"),
        ("pytest", "8.3.4", "pypi/pipfile-lock-dev"),
    ]


def test_parse_backend_ecosystem_manifests():
    go_mod = """
    module example.com/app
    require (
      github.com/gin-gonic/gin v1.10.0
      golang.org/x/crypto v0.24.0 // indirect
    )
    """
    pom_xml = """
    <project>
      <properties><spring.version>6.1.0</spring.version></properties>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
          <version>${spring.version}</version>
        </dependency>
      </dependencies>
    </project>
    """
    build_gradle = """
    dependencies {
      implementation 'org.springframework:spring-core:6.1.0'
      testImplementation group: 'junit', name: 'junit', version: '4.13.2'
    }
    """
    cargo_toml = """
    [dependencies]
    serde = "1.0.190"
    tokio = { version = "1.37.0", features = ["full"] }
    local = { path = "../local" }
    """
    csproj = """
    <Project>
      <ItemGroup>
        <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
      </ItemGroup>
    </Project>
    """
    composer_json = json.dumps(
        {
            "require": {"php": "^8.2", "laravel/framework": "^11.0"},
            "require-dev": {"phpunit/phpunit": "^11.0"},
        }
    )

    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("go_mod", go_mod)["components"]] == [
        ("github.com/gin-gonic/gin", "1.10.0", "go/module"),
        ("golang.org/x/crypto", "0.24.0", "go/module"),
    ]
    assert ManifestParserService.parse("pom_xml", pom_xml)["components"][0] == {
        "category": "Package",
        "key": "library",
        "name": "org.springframework:spring-core",
        "version": "6.1.0",
        "scope": "maven/pom",
    }
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("build_gradle", build_gradle)["components"]] == [
        ("org.springframework:spring-core", "6.1.0", "gradle/implementation"),
        ("junit:junit", "4.13.2", "gradle/testImplementation"),
    ]
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("cargo_toml", cargo_toml)["components"]] == [
        ("serde", "1.0.190", "cargo/runtime"),
        ("tokio", "1.37.0", "cargo/runtime"),
    ]
    assert ManifestParserService.parse("csproj", csproj)["components"][0]["name"] == "Newtonsoft.Json"
    assert [(item["name"], item["version"], item["scope"]) for item in ManifestParserService.parse("composer_json", composer_json)["components"]] == [
        ("laravel/framework", "11.0", "composer/runtime"),
        ("phpunit/phpunit", "11.0", "composer/development"),
    ]


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
