import base64
import os
import re

import requests

from tracker.services.manifest_parser_service import ManifestParserService


class GitHubRepoImportService:
    """Import dependency manifests from a public GitHub repository."""

    API_ROOT = "https://api.github.com"
    MANIFESTS = (
        ("package-lock.json", "package_lock_json"),
        ("yarn.lock", "yarn_lock"),
        ("pnpm-lock.yaml", "pnpm_lock"),
        ("package.json", "package_json"),
        ("poetry.lock", "poetry_lock"),
        ("Pipfile.lock", "pipfile_lock"),
        ("requirements.txt", "requirements_txt"),
        ("pyproject.toml", "pyproject_toml"),
        ("go.mod", "go_mod"),
        ("pom.xml", "pom_xml"),
        ("build.gradle", "build_gradle"),
        ("build.gradle.kts", "build_gradle"),
        ("Cargo.toml", "cargo_toml"),
        ("composer.json", "composer_json"),
    )

    def __init__(self, token: str | None = None, timeout: int = 15):
        self.token = os.getenv("GITHUB_TOKEN", "") if token is None else token
        self.timeout = timeout

    def import_repository(self, repo_url: str) -> dict:
        parsed = self.parse_repo_url(repo_url)
        if not parsed:
            return {
                "components": [],
                "warnings": [],
                "files": [],
                "error": "Enter a valid GitHub repository URL.",
            }

        owner, repo = parsed
        repo_info = self._get_json(f"/repos/{owner}/{repo}")
        if repo_info.get("error"):
            return {
                "components": [],
                "warnings": [],
                "files": [],
                "error": repo_info["error"],
            }

        default_branch = repo_info.get("default_branch") or "main"
        contributors = self.list_contributors(owner, repo)
        components = []
        warnings = []
        files = []
        seen = set()

        for path, manifest_type in self.MANIFESTS:
            content_result = self._get_manifest_content(owner, repo, path, default_branch)
            if content_result.get("missing"):
                continue
            if content_result.get("error"):
                warnings.append(f"{path}: {content_result['error']}")
                continue

            parse_result = ManifestParserService.parse(manifest_type, content_result["content"])
            if parse_result.get("error"):
                warnings.append(f"{path}: {parse_result['error']}")
                continue

            files.append(path)
            warnings.extend([f"{path}: {warning}" for warning in parse_result.get("warnings", [])])
            for component in parse_result.get("components", []):
                dedupe_key = (
                    component.get("scope", "").split("/", 1)[0],
                    component.get("name", "").lower(),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                components.append(component)

        if not components:
            return {
                "components": [],
                "warnings": warnings,
                "files": files,
                "error": "No supported dependency manifests were found in the repository root.",
                "repository": f"{owner}/{repo}",
                "default_branch": default_branch,
                "project_name": repo,
                "contributors": contributors,
            }

        return {
            "components": components,
            "warnings": warnings,
            "files": files,
            "error": "",
            "repository": f"{owner}/{repo}",
            "default_branch": default_branch,
            "project_name": repo,
            "contributors": contributors,
        }


    MAX_CONTRIBUTORS = 10

    def list_contributors(self, owner: str, repo: str) -> list[str]:
        """Top contributor logins, most commits first. Never raises."""
        try:
            response = requests.get(
                f"{self.API_ROOT}/repos/{owner}/{repo}/contributors",
                headers=self._headers(),
                params={"per_page": self.MAX_CONTRIBUTORS, "anon": "0"},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return []

        if response.status_code >= 400:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []

        if not isinstance(payload, list):
            return []

        logins = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "Bot":
                continue
            login = (entry.get("login") or "").strip()
            if login and login not in logins:
                logins.append(login)
        return logins[: self.MAX_CONTRIBUTORS]

    @staticmethod
    def parse_repo_url(repo_url: str) -> tuple[str, str] | None:
        value = (repo_url or "").strip()
        match = re.match(
            r"^(?:https?://)?github\.com/([^/\s]+)/([^/\s#?]+)",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        owner = match.group(1).strip()
        repo = match.group(2).strip().removesuffix(".git")
        if not owner or not repo:
            return None
        return owner, repo

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "LibTrack-AI",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_json(self, path: str) -> dict:
        try:
            response = requests.get(
                f"{self.API_ROOT}{path}",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return {"error": f"GitHub request failed: {exc}"}

        if response.status_code == 404:
            return {"error": "GitHub repository was not found or is not accessible."}
        if response.status_code == 403:
            return {"error": "GitHub API rate limit or permission denied."}
        if response.status_code >= 400:
            return {"error": f"GitHub API returned HTTP {response.status_code}."}

        try:
            return response.json()
        except ValueError:
            return {"error": "GitHub API returned invalid JSON."}

    def _get_manifest_content(self, owner: str, repo: str, path: str, ref: str) -> dict:
        payload = self._get_json(f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")
        if payload.get("error"):
            if "not found" in payload["error"].lower():
                return {"missing": True}
            return payload

        encoded = payload.get("content", "")
        encoding = payload.get("encoding", "")
        if encoding != "base64" or not encoded:
            return {"error": "unsupported GitHub content response."}

        try:
            content = base64.b64decode(encoded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return {"error": "manifest content is not valid UTF-8 text."}

        return {"content": content}
