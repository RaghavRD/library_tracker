import json
import re


class ManifestParserService:
    """Parse dependency manifest content into stack component rows."""

    SUPPORTED_TYPES = {"package_json", "requirements_txt"}
    NPM_SECTIONS = (
        ("dependencies", "runtime"),
        ("devDependencies", "development"),
        ("peerDependencies", "peer"),
        ("optionalDependencies", "optional"),
    )

    @classmethod
    def parse(cls, manifest_type: str, content: str) -> dict:
        manifest_type = (manifest_type or "").strip()
        content = content or ""

        if manifest_type not in cls.SUPPORTED_TYPES:
            return {
                "components": [],
                "warnings": [],
                "error": "Unsupported manifest type.",
            }

        if not content.strip():
            return {
                "components": [],
                "warnings": [],
                "error": "Manifest content is empty.",
            }

        if manifest_type == "package_json":
            return cls._parse_package_json(content)
        return cls._parse_requirements_txt(content)

    @classmethod
    def _parse_package_json(cls, content: str) -> dict:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            return {
                "components": [],
                "warnings": [],
                "error": f"Invalid package.json: {exc.msg}.",
            }

        if not isinstance(payload, dict):
            return {
                "components": [],
                "warnings": [],
                "error": "package.json must contain a JSON object.",
            }

        components = []
        warnings = []
        seen = set()

        for section, scope in cls.NPM_SECTIONS:
            dependencies = payload.get(section) or {}
            if not isinstance(dependencies, dict):
                warnings.append(f"Ignored {section}: expected an object.")
                continue

            for name, raw_version in dependencies.items():
                package_name = str(name).strip()
                normalized_version = cls._normalize_version_spec(str(raw_version).strip())
                if not package_name:
                    continue
                if not normalized_version:
                    warnings.append(f"Skipped {package_name}: unsupported version spec '{raw_version}'.")
                    continue

                key = package_name.lower()
                if key in seen:
                    continue
                seen.add(key)
                components.append(
                    {
                        "category": "Package",
                        "key": "library",
                        "name": package_name,
                        "version": normalized_version,
                        "scope": f"npm/{scope}",
                    }
                )

        return {
            "components": components,
            "warnings": warnings,
            "error": "" if components else "No pinned npm dependencies were found.",
        }

    @classmethod
    def _parse_requirements_txt(cls, content: str) -> dict:
        components = []
        warnings = []
        seen = set()

        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line = cls._strip_inline_comment(raw_line).strip()
            if not line or line.startswith(("-", "#")):
                continue

            match = re.match(
                r"^([A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)\s*(===|==|~=|>=|<=|>|<|!=)\s*([^;\s]+)",
                line,
            )
            if not match:
                warnings.append(f"Line {line_number}: skipped unpinned or unsupported requirement.")
                continue

            package_name = match.group(1).split("[", 1)[0]
            operator = match.group(2)
            raw_version = match.group(3)
            normalized_version = cls._normalize_version_spec(raw_version)
            if not normalized_version:
                warnings.append(f"Line {line_number}: skipped unsupported version spec '{raw_version}'.")
                continue

            key = package_name.lower()
            if key in seen:
                continue
            seen.add(key)
            scope = "pypi/pinned" if operator in {"==", "==="} else f"pypi/{operator}"
            components.append(
                {
                    "category": "Package",
                    "key": "library",
                    "name": package_name,
                    "version": normalized_version,
                    "scope": scope,
                }
            )

        return {
            "components": components,
            "warnings": warnings,
            "error": "" if components else "No pinned Python dependencies were found.",
        }

    @staticmethod
    def _strip_inline_comment(line: str) -> str:
        in_quote = False
        quote_char = ""
        for index, char in enumerate(line):
            if char in {"'", '"'}:
                if in_quote and quote_char == char:
                    in_quote = False
                    quote_char = ""
                elif not in_quote:
                    in_quote = True
                    quote_char = char
            if char == "#" and not in_quote and (index == 0 or line[index - 1].isspace()):
                return line[:index]
        return line

    @staticmethod
    def _normalize_version_spec(spec: str) -> str:
        value = (spec or "").strip().strip("'\"")
        if not value:
            return ""

        lowered = value.lower()
        if lowered in {"latest", "*"}:
            return ""
        if lowered.startswith(("file:", "git+", "http://", "https://", "github:", "workspace:", "link:")):
            return ""

        # Use the first concrete version from common semver/PEP 440 ranges.
        match = re.search(r"\d+(?:[._-]?\d+)*(?:[a-zA-Z]+\.?\d*)?(?:[-+][A-Za-z0-9_.-]+)?", value)
        if not match:
            return ""
        return match.group(0).lstrip("v")
