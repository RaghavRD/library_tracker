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

# Common programming languages (not libraries)
_PROGRAMMING_LANGUAGES = {
    "python", "javascript", "java", "go", "ruby", "php", "rust", 
    "typescript", "c++", "c#", "kotlin", "swift", "scala", "r",
    "perl", "lua", "dart", "elixir", "haskell", "clojure", "node.js",
    "nodejs", "node", "dotnet", ".net"
}

# Official sites for programming languages
_LANGUAGE_OFFICIAL_SITES = {
    "python": "python.org",
    "javascript": "developer.mozilla.org",
    "node.js": "nodejs.org",
    "nodejs": "nodejs.org", 
    "node": "nodejs.org",
    "java": "oracle.com/java OR openjdk.org",
    "go": "go.dev",
    "ruby": "ruby-lang.org",
    "php": "php.net",
    "rust": "rust-lang.org",
    "typescript": "typescriptlang.org",
    "kotlin": "kotlinlang.org",
    "swift": "swift.org",
    "dotnet": "dotnet.microsoft.com",
    ".net": "dotnet.microsoft.com",
}

# Common tools, services, and CLIs (not libraries)
_TOOLS_AND_SERVICES = {
    "docker", "kubernetes", "k8s", "kubectl", "nginx", "apache", "httpd",
    "ansible", "terraform", "jenkins", "gitlab", "github", "prometheus",
    "grafana", "elasticsearch", "kibana", "logstash", "redis", "mongodb",
    "postgresql", "postgres", "mysql", "mariadb", "rabbitmq", "kafka",
    "vault", "consul", "etcd", "haproxy", "traefik", "helm", "argocd",
    "git", "maven", "gradle", "npm", "yarn", "pnpm", "pip", "conda",
    "vscode", "intellij", "eclipse", "vim", "emacs", "aws-cli", "azure-cli",
    "gcloud", "circleci", "travis", "bamboo", "octopus", "spinnaker"
}

# Official sites for tools/services/CLIs
_TOOL_OFFICIAL_SITES = {
    "docker": "docs.docker.com OR docker.com/blog",
    "kubernetes": "kubernetes.io",
    "k8s": "kubernetes.io",
    "kubectl": "kubernetes.io",
    "nginx": "nginx.org OR nginx.com",
    "apache": "httpd.apache.org",
    "httpd": "httpd.apache.org",
    "ansible": "docs.ansible.com",
    "terraform": "developer.hashicorp.com/terraform",
    "jenkins": "jenkins.io",
    "gitlab": "about.gitlab.com OR docs.gitlab.com",
    "github": "github.blog OR docs.github.com",
    "prometheus": "prometheus.io",
    "grafana": "grafana.com",
    "elasticsearch": "elastic.co",
    "kibana": "elastic.co",
    "logstash": "elastic.co",
    "redis": "redis.io",
    "mongodb": "mongodb.com",
    "postgresql": "postgresql.org",
    "postgres": "postgresql.org",
    "mysql": "dev.mysql.com",
    "mariadb": "mariadb.org",
    "rabbitmq": "rabbitmq.com",
    "kafka": "kafka.apache.org",
    "vault": "vaultproject.io",
    "consul": "consul.io",
    "etcd": "etcd.io",
    "haproxy": "haproxy.org",
    "traefik": "traefik.io",
    "helm": "helm.sh",
    "argocd": "argo-cd.readthedocs.io",
    "git": "git-scm.com",
    "maven": "maven.apache.org",
    "gradle": "gradle.org",
    "npm": "docs.npmjs.com OR npmjs.com/package/npm",
    "yarn": "yarnpkg.com",
    "pnpm": "pnpm.io",
    "pip": "pip.pypa.io",
    "conda": "docs.conda.io",
    "aws-cli": "docs.aws.amazon.com/cli",
    "azure-cli": "docs.microsoft.com/cli/azure",
    "gcloud": "cloud.google.com/sdk/gcloud",
}

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
                # Filter out likely years/dates (e.g. 2025.12)
                # Heuristic: if major version > 200, assume it's a date/year, unless length is small (like build number)
                # But simple year check is safest for now matching the bug report (2025.x).
                try:
                    parts = match.split('.')
                    if parts and parts[0].isdigit() and int(parts[0]) > 200:
                        continue
                except (ValueError, IndexError):
                    pass
                    
                versions.append(match)
        return versions

    # ---------------------------------------------
    @staticmethod
    def _score_link(link: str, is_language: bool = False, result_date: str = "") -> int:
        """Assign a priority score to favor official sources and recent results."""
        if not link:
            return 0
        
        score = 1
        host = link.split("/")[2] if "://" in link else link.split("/")[0]
        
        # Boost official package registry sites
        for domain, base_score in _OFFICIAL_HOST_WEIGHTS.items():
            if domain in host:
                score += base_score
        
        # Extra boost for official language sites when searching for languages
        if is_language:
            for lang_site in _LANGUAGE_OFFICIAL_SITES.values():
                # Extract just the domain (e.g., "python.org" from "python.org")
                main_domain = lang_site.split(" OR ")[0].strip()
                if main_domain in host:
                    score += 10  # Heavily favor official language sites
            
            # Also check tool sites (in case a tool is being searched as a language)
            for tool_site in _TOOL_OFFICIAL_SITES.values():
                main_domain = tool_site.split(" OR ")[0].strip()
                if main_domain in host:
                    score += 10  # Heavily favor official tool sites too
        
        # Boost recent results (if date is available)
        if result_date:
            try:
                from datetime import datetime
                # Try to parse the date
                result_datetime = datetime.strptime(result_date[:10], "%Y-%m-%d")
                days_old = (datetime.now() - result_datetime).days
                
                if days_old < 30:  # Less than a month old
                    score += 5
                elif days_old < 90:  # Less than 3 months old
                    score += 3
                elif days_old < 180:  # Less than 6 months old
                    score += 1
            except Exception:
                pass  # If date parsing fails, just skip the bonus
        
        return score

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
                # Double check for year-like numbers
                if parsed.major > 200:
                    continue
                best = parsed
                best_raw = raw
        return best_raw

    # ---------------------------------------------
    @staticmethod
    def _is_programming_language(name: str) -> bool:
        """Check if the component is a programming language vs a library."""
        return name.lower().strip() in _PROGRAMMING_LANGUAGES

    # ---------------------------------------------
    @staticmethod
    def _is_tool_or_service(name: str) -> bool:
        """Check if the component is a tool/service/CLI."""
        return name.lower().strip() in _TOOLS_AND_SERVICES

    # ---------------------------------------------
    @staticmethod
    def _get_time_filter() -> str:
        """Get date filter for recent results (last 3 months)."""
        from datetime import datetime, timedelta
        three_months_ago = datetime.now() - timedelta(days=90)
        return three_months_ago.strftime("%Y-%m-%d")

    # ---------------------------------------------
    def search_library(self, library: str, current_version: str | None = None, component_type: str = "library") -> dict:
        """
        Searches the web for the most recent info about a given library or language.
        
        Args:
            library: Name of the library or language
            current_version: Current version to compare against
            component_type: "library" or "language" (auto-detected if not specified)
        
        Returns:
            dict with search results, filtered results, and version candidates
        """

        if not library or not isinstance(library, str):
            return {"error": "Invalid library name", "results": []}

        # Auto-detect component type
        is_language = component_type == "language" or self._is_programming_language(library)
        is_tool = component_type == "tool" or self._is_tool_or_service(library)
        
        # Determine final category
        if is_language:
            category = "language"
        elif is_tool:
            category = "tool"
        else:
            category = "library"
        
        time_filter = self._get_time_filter()

        if self.debug:
            print(f"🔍 Fetching {category} data for '{library}' (current={current_version})...")

        # Different query strategies based on category
        if is_language:
            # For programming languages, search official sites
            official_site = _LANGUAGE_OFFICIAL_SITES.get(library.lower(), f"{library}.org")
            base_queries = [
                f"{library} latest version site:{official_site}",
                f"{library} download latest release site:{official_site}",
                f"{library} release notes after:{time_filter}",
                f"{library} changelog what's new {datetime.now().year}",
                f"{library} current version official",
            ]
        elif is_tool:
            # For tools/services/CLIs, search official documentation sites
            official_site = _TOOL_OFFICIAL_SITES.get(library.lower(), f"{library}.io OR {library}.org")
            base_queries = [
                f"{library} latest version site:{official_site}",
                f"{library} release notes site:{official_site}",
                f"{library} download latest after:{time_filter}",
                f"{library} changelog {datetime.now().year} site:{official_site}",
                f"{library} stable version official documentation",
            ]
        else:
            # For libraries, search package registries and GitHub
            base_queries = [
                f"{library} latest release after:{time_filter} site:pypi.org OR site:npmjs.com OR site:rubygems.org",
                f"{library} changelog OR release notes site:github.com OR site:gitlab.com",
                f"{library} new features after:{time_filter}",
                f"{library} stable release what's new {datetime.now().year}",
                f"{library} documentation latest version site:readthedocs.io",
            ]

        # Common future update queries for both languages and libraries
        future_queries = [
            f"{library} roadmap next release OR upcoming changes",
            f"{library} release candidate OR beta announcement after:{time_filter}",
        ]

        responses = [self._call_serper(q) for q in base_queries]
        future_responses = [self._call_serper(q) for q in future_queries]
        merged = self._merge_results(*responses, *future_responses)

        filtered = []
        future_updates = []
        keywords = ("release", "version", "changelog", "notes", "update", "download")
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
            result["relevance_score"] = self._score_link(
                result.get("link", ""), 
                is_language=(is_language or is_tool),  # Both languages and tools get official site boost
                result_date=result.get("date", "")
            ) + len(versions_found)

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
