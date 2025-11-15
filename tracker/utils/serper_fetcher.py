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

        responses = [self._call_serper(q) for q in base_queries]
        merged = self._merge_results(*responses)

        filtered = []
        keywords = ("release", "version", "changelog", "notes", "update")
        version_pattern = re.compile(r"\b\d+(\.\d+){1,2}\b")

        for r in merged.get("results", []):
            title = (r.get("title") or "").lower()
            link = (r.get("link") or "").lower()
            snippet = (r.get("snippet") or "").lower()

            if any(k in title or k in snippet or k in link for k in keywords):
                if current_version:
                    # Extract all version-like strings
                    found_versions = version_pattern.findall(r.get("snippet", "") + " " + r.get("title", ""))
                    for fv in re.findall(r"\d+(\.\d+){1,2}", r.get("snippet", "") + " " + r.get("title", "")):
                        try:
                            if pkg_version.parse(fv) > pkg_version.parse(current_version):
                                filtered.append(r)
                                break
                        except Exception:
                            continue
                else:
                    filtered.append(r)

        merged["filtered"] = filtered
        merged["library"] = library
        merged["source_count"] = len(filtered)
        merged["fetched_at"] = datetime.utcnow().isoformat()

        if self.debug:
            print(f"✅ Filtered {len(filtered)} higher-version results for {library}")

        return merged
    
# Manual test when running directly
# if __name__ == "__main__":
#     fetcher = SerperFetcher(debug=True)
#     result = fetcher.search_library("pandas")
#     print(json.dumps(result, indent=2)[:4000])

