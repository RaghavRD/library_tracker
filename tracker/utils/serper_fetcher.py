import os
import json
import requests
import re
from packaging import version as pkg_version
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# ✅ Locate .env manually (robust)
BASE_DIR = Path(__file__).resolve().parents[2]
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"✅ [serper_fetcher] Loaded .env from: {env_path}")
else:
    print(f"⚠️ [serper_fetcher] .env not found at expected path: {env_path}")

# ✅ Default Serper endpoint
SERPER_URL = os.getenv("SERPER_SEARCH_URL", "https://google.serper.dev/search")

# Host scoring to favor official sources when possible
_OFFICIAL_HOST_WEIGHTS = {
    "github.com": 3,
    "gitlab.com": 3,
    "pypi.org": 3,
    "npmjs.com": 3,
    "rubygems.org": 3,
    "python.org": 2,
    "docs.microsoft.com": 2,
    "developer.mozilla.org": 2,
}

_FUTURE_KEYWORDS = (
    "upcoming",
    "roadmap",
    "planned",
    "preview",
    "beta",
    "next release",
    "release candidate",
    "rc",
    "nightly",
    "next version",
    "launch",
    "ga",
    "general availability",
)

# --- Enhanced Fetcher Class ---
class SerperFetcher:
    """
    Enhanced Serper.dev fetcher that retrieves detailed and accurate data
    about a library — including release notes, latest version, and changelog
    information — by combining multiple search facets.
    """

    def __init__(self, timeout: int = 15, debug: bool = False):
        self.api_key = os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise RuntimeError("SERPER_API_KEY missing in .env")
        self.timeout = timeout
        self.debug = debug

    # ---------------------------------------------
    def _call_serper(self, query: str) -> dict:
        """Internal helper to call Serper API."""
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": 10, "gl": "us"}
        try:
            resp = requests.post(SERPER_URL, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            data["query"] = query  # keep track of which prompt produced the data
            if self.debug:
                print(f"✅ Serper success for query: {query}")
            return data
        except requests.HTTPError as e:
            msg = f"HTTP {resp.status_code}: {resp.text}" if 'resp' in locals() else str(e)
            if self.debug:
                print(f"❌ Serper error: {msg}")
            return {"error": msg, "results": []}
        except Exception as e:
            return {"error": str(e), "results": []}

    # ---------------------------------------------
    def _merge_results(self, *responses: dict) -> dict:
        """Merge multiple Serper responses into a single coherent structure."""
        merged = {"results": [], "sources": []}
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            for k in ("organic", "news", "videos", "answerBox", "knowledgeGraph"):
                if k in resp:
                    merged["results"].extend(resp.get(k, []))
            merged["sources"].append({"query": resp.get("query", ""), "count": len(resp.get("organic", []))})
        merged["timestamp"] = datetime.utcnow().isoformat()
        return merged

    # ---------------------------------------------
    @staticmethod
    def _dedupe_results(results: list[dict]) -> list[dict]:
        """Remove duplicate links while preserving order."""
        seen = set()
        deduped = []
        for item in results:
            link = (item.get("link") or "").split("#")[0]
            if not link or link in seen:
                continue
            seen.add(link)
            deduped.append(item)
        return deduped

    # ---------------------------------------------
    @staticmethod
    def _extract_versions(text: str) -> list[str]:
        """Return unique version-like strings from text."""
        if not text:
            return []
        pattern = re.compile(r"\b\d+(?:\.\d+){1,3}(?:[a-zA-Z0-9\-]+)?\b")
        versions = []
        for match in pattern.findall(text):
            if match not in versions:
                versions.append(match)
        return versions

    # ---------------------------------------------
    @staticmethod
    def _score_link(link: str) -> int:
        """Assign a priority score to favor official sources."""
        if not link:
            return 0
        host = link.split("/")[2] if "://" in link else link.split("/")[0]
        for domain, score in _OFFICIAL_HOST_WEIGHTS.items():
            if domain in host:
                return score
        return 1

    # ---------------------------------------------
    @staticmethod
    def _is_future_focused(text: str) -> bool:
        """Detect if the snippet/title is describing upcoming releases."""
        if not text:
            return False
        lower = text.lower()
        return any(keyword in lower for keyword in _FUTURE_KEYWORDS)

    # ---------------------------------------------
    @staticmethod
    def _pick_latest_version(candidates: list[str]) -> str:
        """Select the highest semantic version from collected candidates."""
        best = None
        best_raw = ""
        for raw in candidates:
            try:
                parsed = pkg_version.parse(raw)
            except Exception:
                continue
            if best is None or parsed > best:
                best = parsed
                best_raw = raw
        return best_raw

    # ---------------------------------------------
    def search_library(self, library: str, current_version: str | None = None) -> dict:
        """
        Searches the web for the most recent info about a given library.
        If `current_version` is provided, filters results that mention a higher version.
        """

        if not library or not isinstance(library, str):
            return {"error": "Invalid library name", "results": []}

        if self.debug:
            print(f"🔍 Fetching library data for '{library}' (current={current_version})...")

        base_queries = [
            f"{library} latest release version site:pypi.org OR site:npmjs.com OR site:rubygems.org",
            f"{library} changelog OR release notes site:github.com OR site:gitlab.com",
            f"{library} new features OR breaking changes site:dev.to OR site:medium.com",
            f"{library} stable release date OR updated site:python.org OR site:angular.io OR site:reactjs.org",
            f"{library} documentation site:readthedocs.io OR site:{library}.org",
        ]

        future_queries = [
            f"{library} roadmap next {library} release OR upcoming changes",
            f"{library} release candidate OR beta announcement",
        ]

        responses = [self._call_serper(q) for q in base_queries]
        future_responses = [self._call_serper(q) for q in future_queries]
        merged = self._merge_results(*responses, *future_responses)

        filtered = []
        future_updates = []
        keywords = ("release", "version", "changelog", "notes", "update")
        version_candidates = []

        all_results = self._dedupe_results(merged.get("results", []))

        for result in all_results:
            text_blob = " ".join(
                filter(
                    None,
                    [
                        result.get("title", ""),
                        result.get("snippet", ""),
                        result.get("date", ""),
                    ],
                )
            )
            versions_found = self._extract_versions(text_blob)
            result["versions_found"] = versions_found
            result["relevance_score"] = self._score_link(result.get("link", "")) + len(versions_found)

            if versions_found:
                version_candidates.extend(versions_found)

            title = (result.get("title") or "").lower()
            link = (result.get("link") or "").lower()
            snippet = (result.get("snippet") or "").lower()
            contains_keyword = any(k in title or k in snippet or k in link for k in keywords)

            if self._is_future_focused(text_blob):
                future_updates.append(result)
                continue

            if contains_keyword:
                if current_version:
                    for version_str in versions_found:
                        try:
                            if pkg_version.parse(version_str) > pkg_version.parse(current_version):
                                filtered.append(result)
                                break
                        except Exception:
                            continue
                else:
                    filtered.append(result)

        merged["filtered"] = filtered
        merged["future_updates"] = future_updates[:5]  # keep response size manageable
        merged["library"] = library
        merged["source_count"] = len(filtered)
        merged["fetched_at"] = datetime.utcnow().isoformat()
        merged["latest_version_candidate"] = self._pick_latest_version(version_candidates)

        if self.debug:
            future_msg = f", future updates: {len(future_updates)}" if future_updates else ""
            print(f"✅ Filtered {len(filtered)} higher-version results for {library}{future_msg}")

        return merged
    
# Manual test when running directly
# if __name__ == "__main__":
#     fetcher = SerperFetcher(debug=True)
#     result = fetcher.search_library("pandas")
#     print(json.dumps(result, indent=2)[:4000])
