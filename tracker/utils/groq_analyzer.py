import os
import json
import re
from groq import Groq
from dotenv import load_dotenv
from packaging import version as pkg_version
from pathlib import Path

# ✅ Load environment early
BASE_DIR = Path(__file__).resolve().parents[2]
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"✅ [groq_analyzer] Loaded .env from: {env_path}")
else:
    print(f"⚠️ [groq_analyzer] .env not found at: {env_path}")

# System message that tells Groq to *only* respond in JSON
_SYSTEM_PROMPT = (
    "You are a precise AI release analyzer. "
    "You always respond in valid JSON ONLY (no markdown, no explanations). "
    "Your task: extract and summarize the most relevant version info from the provided search results. "
    "CRITICAL: ALWAYS prioritize the NEWEST version from the most recent and official sources. "
    "Ignore results older than 6 months unless no recent information exists. "
    "If multiple versions are found, return the HIGHEST version number."
)

_JSON_SCHEMA_HINT = """
Return JSON like this:
{
  "library": "<name>",
  "version": "<latest_version_number>",
  "category": "major|minor|future",
  "is_released": true|false,
  "confidence": 0-100,
  "expected_date": "YYYY-MM-DD or empty",
  "summary": "3-4 concise bullet points or sentences about new features or changes",
  "release_date": "YYYY-MM-DD or empty if unknown",
  "source": "<official URL>"
}

CRITICAL RULES:
1. Use "future" category ONLY if the version is NOT yet officially released (beta, RC, planned, announced, roadmap).
2. Use "major" or "minor" ONLY for officially released stable versions.
3. Set "is_released" to false for future/planned versions, true for released versions.
4. Set "expected_date" (YYYY-MM-DD format) for future versions if mentioned in sources.
5. Set "release_date" (YYYY-MM-DD format) for released versions only.
6. Provide "confidence" score (0-100) based on source reliability:
   - 90-100: Official documentation/blog from maintainers (github.com/org/repo/releases, official .org sites)
   - 70-89: Reputable tech news sites (techcrunch, ars technica, the verge)
   - 50-69: Community forums, Reddit, dev.to, medium blogs
   - 0-49: Speculation, rumors, unverified sources
7. If you find BOTH a released version AND a future version in results, return the RELEASED version and mention the future version in the summary.
8. IMPORTANT: Cross-check your detected version against the 'latest_version_candidate' hint provided. If the hint shows a higher version, use that version instead.
9. When comparing versions, always select the HIGHEST semantic version (e.g., 3.14.2 > 3.11.7 > 3.11.1).
"""

MAJOR_SIGNALS = {
    "breaking",
    "deprecated",
    "security",
    "cve",
    "vulnerability",
    "removed",
    "migration",
    "refactor",
    "major",
    "incompatible",
    "upgrade required",
    "critical",
}

# --- Utility Functions ---
def _clean_version(v: str) -> str:
    """Normalize version strings like 'v2.1.0-beta' → '2.1.0'."""
    if not v:
        return ""
    v = v.strip().lower().replace("version", "").replace("v", "").strip()
    v = re.sub(r"[^0-9.\-]", "", v)
    parts = v.split(".")
    if len(parts) > 3:
        parts = parts[:3]
    return ".".join([p for p in parts if p])

def _coerce_category(text: str) -> str:
    """Infer major/minor update type based on text cues."""
    if not text:
        return "minor"
    t = text.lower()
    if any(w in t for w in MAJOR_SIGNALS):
        return "major"
    return "minor"

def _extract_json(s: str) -> dict:
    """Try to extract the first JSON object from text safely."""
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}

# --- Core Analyzer Class ---
class GroqAnalyzer:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY missing in .env")

        self.client = Groq(api_key=api_key)
        # ✅ Updated model list — choose safest available
        # self.model = os.getenv("GROQ_MODEL", "llama-3.2-11b-text")
        self.model = os.getenv("GROQ_MODEL")
        self._validate_model()

    def _validate_model(self):
        """Fallback if model is deprecated or unavailable."""
        deprecated = {
            "llama-3.1-70b-versatile",
            "llama-3.2-70b-versatile",
        }
        if self.model in deprecated:
            print(f"⚠️ Model '{self.model}' deprecated. Falling back to 'llama-3.2-11b-text'")
            self.model = "llama-3.2-11b-text"

    def analyze(self, library: str, serper_results: dict) -> dict:
        """
        Analyze Serper results using Groq to extract structured version info.
        """
        if not isinstance(serper_results, dict):
            return {"error": "Invalid Serper result type"}

        serper_text = json.dumps(serper_results.get("filtered") or serper_results, indent=2)[:12000]
        future_updates = serper_results.get("future_updates") or []

        future_snippets = ""
        if future_updates:
            future_lines = []
            for entry in future_updates[:3]:
                title = entry.get("title", "").strip()
                snippet = entry.get("snippet", "").strip()
                link = entry.get("link", "").strip()
                future_lines.append(f"- {title} :: {snippet} ({link})")
            future_snippets = "\nUpcoming / planned releases:\n" + "\n".join(future_lines)

        prompt = (
            f"Analyze the following search results for the library '{library}'. "
            f"Find the latest release version, update type (major/minor), date, and summary.\n\n"
            f"{_JSON_SCHEMA_HINT}\n\n"
            f"Latest version hint from search: {serper_results.get('latest_version_candidate') or 'unknown'}\n"
            f"{future_snippets}\n"
            f"Search Results:\n{serper_text}"
        )

        try:
            comp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = comp.choices[0].message.content
            data = _extract_json(content)
        except Exception as e:
            return {"error": f"Groq request failed: {str(e)}"}

        # --- Normalize Fields ---
        if not isinstance(data, dict):
            data = {}

        data["library"] = library
        data["version"] = _clean_version(str(data.get("version", "")))
        data["summary"] = str(data.get("summary", "")).strip()
        data["release_date"] = str(data.get("release_date", "")).strip()
        data["source"] = str(data.get("source", "")).strip()

        # ===== NEW: Handle future update fields =====
        is_released = data.get("is_released", True)
        if isinstance(is_released, str):
            is_released = is_released.lower() in ("true", "yes", "1")
        data["is_released"] = bool(is_released)
        
        # Extract confidence score
        confidence = data.get("confidence", 50)
        try:
            confidence = int(confidence)
            if confidence < 0 or confidence > 100:
                confidence = 50
        except (ValueError, TypeError):
            confidence = 50
        data["confidence"] = confidence
        
        # Extract expected date for future updates
        expected_date = str(data.get("expected_date", "")).strip()
        data["expected_date"] = expected_date

        # Category logic
        cat = str(data.get("category", "")).lower().strip()
        
        # ===== CRITICAL: Force "future" category if not released =====
        if not data["is_released"]:
            cat = "future"
        elif cat not in {"major", "minor", "future"}:
            cat = _coerce_category(data.get("summary", ""))
        
        data["category"] = cat

        # --- Fallback if version missing but Serper provided candidate ---
        if not data["version"]:
            data["version"] = str(serper_results.get("latest_version_candidate", "")).strip()

        # --- Cross-check against Serper's candidate ---
        candidate_version = str(serper_results.get("latest_version_candidate", "")).strip()
        if data["version"] and candidate_version:
            try:
                groq_ver = pkg_version.parse(data["version"])
                candidate_ver = pkg_version.parse(candidate_version)
                
                if candidate_ver > groq_ver:
                    # Serper found a higher version than Groq detected
                    import logging
                    logger = logging.getLogger('libtrack')
                    logger.warning(
                        f"[{library}] Version mismatch: Groq detected {data['version']}, "
                        f"but Serper found {candidate_version}. Using higher version."
                    )
                    data["version"] = candidate_version
                    # Lower confidence since there's a mismatch
                    data["confidence"] = max(data.get("confidence", 50) - 10, 30)
            except Exception as e:
                # If version comparison fails, prefer Serper's candidate if groq version is invalid
                if candidate_version:
                    try:
                        pkg_version.parse(candidate_version)
                        data["version"] = candidate_version
                    except Exception:
                        pass

        # --- Final sanity check ---
        if data["version"]:
            try:
                pkg_version.parse(data["version"])
            except Exception:
                data["version"] = _clean_version(data["version"])
        
        # print(json.dumps(data, indent=2))

        return data


# ✅ Manual test
if __name__ == "__main__":
    from tracker.utils.serper_fetcher import SerperFetcher

    sf = SerperFetcher(debug=True)
    groq = GroqAnalyzer()

    print("\n=== Testing for library: pandas ===")
    results = sf.search_library("pandas")
    analysis = groq.analyze("pandas", results)
    print(json.dumps(analysis, indent=2))
