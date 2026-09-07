from __future__ import annotations

import logging

import requests
from allauth.socialaccount.models import SocialAccount, SocialToken

logger = logging.getLogger("libtrack")


class GitHubAccountService:
    """Fetch repositories from the currently connected GitHub account."""

    API_ROOT = "https://api.github.com"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def get_access_token(self, user):
        token = (
            SocialToken.objects.select_related("account")
            .filter(account__user=user, account__provider="github")
            .order_by("-expires_at", "-id")
            .first()
        )
        return token.token if token else ""

    def get_account_email(self, user) -> str:
        """Email of the connected GitHub account, falling back to the Django user."""
        account = (
            SocialAccount.objects.filter(user=user, provider="github")
            .order_by("-id")
            .first()
        )
        if account:
            extra = account.extra_data or {}
            email = (extra.get("email") or "").strip()
            if email:
                return email
        return (getattr(user, "email", "") or "").strip()

    def list_repositories(self, user) -> dict:
        token = self.get_access_token(user)
        if not token:
            return {
                "repositories": [],
                "error": "Connect your GitHub account to see repositories.",
            }

        repositories = []
        error = ""
        url = f"{self.API_ROOT}/user/repos"
        params = {
            "per_page": 100,
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "sort": "full_name",
            "direction": "asc",
        }

        while url:
            try:
                response = requests.get(
                    url,
                    headers=self._headers(token),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                return {
                    "repositories": [],
                    "error": f"GitHub request failed: {exc}",
                }

            params = None
            if response.status_code in {401, 403}:
                message = self._extract_error_message(response) or "GitHub repository access was denied."
                return {
                    "repositories": [],
                    "error": message,
                }
            if response.status_code >= 400:
                return {
                    "repositories": [],
                    "error": f"GitHub API returned HTTP {response.status_code}.",
                }

            try:
                payload = response.json()
            except ValueError:
                return {
                    "repositories": [],
                    "error": "GitHub API returned invalid JSON.",
                }

            for repo in payload:
                owner = repo.get("owner") or {}
                repositories.append(
                    {
                        "id": repo.get("id"),
                        "name": repo.get("name", ""),
                        "full_name": repo.get("full_name", ""),
                        "html_url": repo.get("html_url", ""),
                        "private": bool(repo.get("private")),
                        "fork": bool(repo.get("fork")),
                        "archived": bool(repo.get("archived")),
                        "default_branch": repo.get("default_branch", ""),
                        "description": repo.get("description", "") or "",
                        "updated_at": repo.get("updated_at", "") or "",
                        "language": repo.get("language", "") or "",
                        "stars": repo.get("stargazers_count", 0) or 0,
                        "owner_login": owner.get("login", "") or "",
                        "owner_avatar": owner.get("avatar_url", "") or "",
                    }
                )

            url = response.links.get("next", {}).get("url", "")

        repositories.sort(key=lambda item: item["full_name"].casefold())
        return {"repositories": repositories, "error": error}

    def get_repository_for_user(self, user, repo_id: str | int) -> dict:
        repositories_result = self.list_repositories(user)
        if repositories_result.get("error"):
            return {
                "repository": None,
                "error": repositories_result["error"],
            }

        target = str(repo_id).strip()
        if not target:
            return {
                "repository": None,
                "error": "Select a repository from your connected GitHub account.",
            }

        for repository in repositories_result.get("repositories", []):
            if str(repository.get("id")) == target:
                return {
                    "repository": repository,
                    "error": "",
                }

        return {
            "repository": None,
            "error": "Select a repository from your connected GitHub account.",
        }

    def _headers(self, token: str) -> dict:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "LibTrack-AI",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _extract_error_message(self, response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        message = (payload.get("message") or "").strip()
        if message:
            return message
        return ""
