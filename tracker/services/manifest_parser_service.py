import json
import re
import textwrap
import tomllib
import xml.etree.ElementTree as ET


class ManifestParserService:
    """Parse dependency manifest content into stack component rows."""

    SUPPORTED_TYPES = {
        "package_json",
        "package_lock_json",
        "yarn_lock",
        "pnpm_lock",
        "requirements_txt",
        "pyproject_toml",
        "poetry_lock",
        "pipfile_lock",
        "go_mod",
        "pom_xml",
        "build_gradle",
        "cargo_toml",
        "csproj",
        "composer_json",
    }
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
            return cls._empty_result("Unsupported manifest type.")

        if not content.strip():
            return cls._empty_result("Manifest content is empty.")

        parsers = {
            "package_json": cls._parse_package_json,
            "package_lock_json": cls._parse_package_lock_json,
            "yarn_lock": cls._parse_yarn_lock,
            "pnpm_lock": cls._parse_pnpm_lock,
            "requirements_txt": cls._parse_requirements_txt,
            "pyproject_toml": cls._parse_pyproject_toml,
            "poetry_lock": cls._parse_poetry_lock,
            "pipfile_lock": cls._parse_pipfile_lock,
            "go_mod": cls._parse_go_mod,
            "pom_xml": cls._parse_pom_xml,
            "build_gradle": cls._parse_build_gradle,
            "cargo_toml": cls._parse_cargo_toml,
            "csproj": cls._parse_csproj,
            "composer_json": cls._parse_composer_json,
        }
        return parsers[manifest_type](content)

    @classmethod
    def _parse_package_json(cls, content: str) -> dict:
        payload, error = cls._load_json(content, "package.json")
        if error:
            return cls._empty_result(error)
        if not isinstance(payload, dict):
            return cls._empty_result("package.json must contain a JSON object.")

        components = []
        warnings = []
        seen = set()

        for section, scope in cls.NPM_SECTIONS:
            dependencies = payload.get(section) or {}
            if not isinstance(dependencies, dict):
                warnings.append(f"Ignored {section}: expected an object.")
                continue

            for name, raw_version in dependencies.items():
                cls._add_component(
                    components,
                    seen,
                    warnings,
                    name,
                    raw_version,
                    f"npm/{scope}",
                    unsupported_label=str(raw_version),
                )

        return cls._result(components, warnings, "No pinned npm dependencies were found.")

    @classmethod
    def _parse_package_lock_json(cls, content: str) -> dict:
        payload, error = cls._load_json(content, "package-lock.json")
        if error:
            return cls._empty_result(error)
        if not isinstance(payload, dict):
            return cls._empty_result("package-lock.json must contain a JSON object.")

        components = []
        warnings = []
        seen = set()

        packages = payload.get("packages")
        if isinstance(packages, dict):
            for path, data in packages.items():
                if not path or not isinstance(data, dict):
                    continue
                if not path.startswith("node_modules/"):
                    continue
                package_name = path.removeprefix("node_modules/")
                cls._add_component(components, seen, warnings, package_name, data.get("version"), "npm/lockfile")

        dependencies = payload.get("dependencies")
        if isinstance(dependencies, dict):
            for package_name, data in dependencies.items():
                if isinstance(data, dict):
                    cls._add_component(components, seen, warnings, package_name, data.get("version"), "npm/lockfile")

        return cls._result(components, warnings, "No npm lockfile dependencies were found.")

    @classmethod
    def _parse_yarn_lock(cls, content: str) -> dict:
        content = textwrap.dedent(content)
        components = []
        warnings = []
        seen = set()
        current_names = []

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line or line.startswith("#") or line.startswith("__metadata:"):
                continue
            if not raw_line.startswith((" ", "\t")) and line.endswith(":"):
                current_names = [
                    name
                    for name in (cls._npm_name_from_descriptor(part) for part in cls._split_yarn_descriptors(line[:-1]))
                    if name
                ]
                continue
            version_match = re.match(r"^\s+version\s+['\"]?([^'\"\s]+)", raw_line)
            if version_match and current_names:
                for name in current_names:
                    cls._add_component(components, seen, warnings, name, version_match.group(1), "npm/yarn-lock")
                current_names = []

        return cls._result(components, warnings, "No yarn.lock dependencies were found.")

    @classmethod
    def _parse_pnpm_lock(cls, content: str) -> dict:
        content = textwrap.dedent(content)
        components = []
        warnings = []
        seen = set()

        for raw_line in content.splitlines():
            line = raw_line.strip().strip("'\"")
            match = re.match(r"^/((?:@[^/]+/)?[^/@][^@]*)@([^(/:\s]+)", line)
            if match:
                cls._add_component(components, seen, warnings, match.group(1), match.group(2), "npm/pnpm-lock")

        return cls._result(components, warnings, "No pnpm lockfile dependencies were found.")

    @classmethod
    def _parse_requirements_txt(cls, content: str) -> dict:
        components = []
        warnings = []
        seen = set()

        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            line = cls._strip_inline_comment(raw_line).strip()
            if not line or line.startswith(("-", "#")):
                continue

            parsed = cls._parse_python_requirement(line)
            if not parsed:
                warnings.append(f"Line {line_number}: skipped unpinned or unsupported requirement.")
                continue

            package_name, operator, raw_version = parsed
            scope = "pypi/pinned" if operator in {"==", "==="} else f"pypi/{operator}"
            cls._add_component(components, seen, warnings, package_name, raw_version, scope)

        return cls._result(components, warnings, "No pinned Python dependencies were found.")

    @classmethod
    def _parse_pyproject_toml(cls, content: str) -> dict:
        payload, error = cls._load_toml(content, "pyproject.toml")
        if error:
            return cls._empty_result(error)

        components = []
        warnings = []
        seen = set()

        project = payload.get("project") if isinstance(payload, dict) else {}
        if isinstance(project, dict):
            cls._add_python_requirement_list(components, seen, warnings, project.get("dependencies"), "pypi/project")
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for group, deps in optional.items():
                    cls._add_python_requirement_list(components, seen, warnings, deps, f"pypi/optional:{group}")

        tool = payload.get("tool", {}) if isinstance(payload, dict) else {}
        poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
        if isinstance(poetry, dict):
            cls._add_poetry_dependency_table(components, seen, warnings, poetry.get("dependencies"), "pypi/poetry")
            cls._add_poetry_dependency_table(
                components,
                seen,
                warnings,
                poetry.get("dev-dependencies"),
                "pypi/poetry-dev",
            )
            groups = poetry.get("group")
            if isinstance(groups, dict):
                for group_name, group_data in groups.items():
                    if isinstance(group_data, dict):
                        cls._add_poetry_dependency_table(
                            components,
                            seen,
                            warnings,
                            group_data.get("dependencies"),
                            f"pypi/poetry-group:{group_name}",
                        )

        return cls._result(components, warnings, "No Python project dependencies were found.")

    @classmethod
    def _parse_poetry_lock(cls, content: str) -> dict:
        payload, error = cls._load_toml(content, "poetry.lock")
        if error:
            return cls._empty_result(error)

        components = []
        warnings = []
        seen = set()

        packages = payload.get("package") if isinstance(payload, dict) else []
        if isinstance(packages, list):
            for package in packages:
                if isinstance(package, dict):
                    cls._add_component(components, seen, warnings, package.get("name"), package.get("version"), "pypi/poetry-lock")

        return cls._result(components, warnings, "No poetry.lock dependencies were found.")

    @classmethod
    def _parse_pipfile_lock(cls, content: str) -> dict:
        payload, error = cls._load_json(content, "Pipfile.lock")
        if error:
            return cls._empty_result(error)
        if not isinstance(payload, dict):
            return cls._empty_result("Pipfile.lock must contain a JSON object.")

        components = []
        warnings = []
        seen = set()

        for section, scope in (("default", "pypi/pipfile-lock"), ("develop", "pypi/pipfile-lock-dev")):
            dependencies = payload.get(section) or {}
            if not isinstance(dependencies, dict):
                continue
            for package_name, data in dependencies.items():
                raw_version = data.get("version") if isinstance(data, dict) else data
                cls._add_component(components, seen, warnings, package_name, raw_version, scope)

        return cls._result(components, warnings, "No Pipfile.lock dependencies were found.")

    @classmethod
    def _parse_go_mod(cls, content: str) -> dict:
        components = []
        warnings = []
        seen = set()
        in_require_block = False

        for raw_line in content.splitlines():
            line = cls._strip_go_comment(raw_line).strip()
            if not line:
                continue
            if line == "require (":
                in_require_block = True
                continue
            if in_require_block and line == ")":
                in_require_block = False
                continue
            if line.startswith("require "):
                line = line.removeprefix("require ").strip()
            elif not in_require_block:
                continue

            parts = line.split()
            if len(parts) >= 2:
                cls._add_component(components, seen, warnings, parts[0], parts[1], "go/module")

        return cls._result(components, warnings, "No Go module dependencies were found.")

    @classmethod
    def _parse_pom_xml(cls, content: str) -> dict:
        root, error = cls._load_xml(content, "pom.xml")
        if error:
            return cls._empty_result(error)

        components = []
        warnings = []
        seen = set()
        properties = cls._xml_properties(root)

        for dependency in cls._xml_descendants(root, "dependency"):
            group_id = cls._xml_child_text(dependency, "groupId")
            artifact_id = cls._xml_child_text(dependency, "artifactId")
            version = cls._resolve_property(cls._xml_child_text(dependency, "version"), properties)
            if group_id and artifact_id and version:
                cls._add_component(components, seen, warnings, f"{group_id}:{artifact_id}", version, "maven/pom")

        return cls._result(components, warnings, "No Maven dependencies were found.")

    @classmethod
    def _parse_build_gradle(cls, content: str) -> dict:
        components = []
        warnings = []
        seen = set()

        shorthand_pattern = re.compile(
            r"(?P<config>\w+)\s*(?:\(?\s*)?['\"](?P<group>[A-Za-z0-9_.-]+):(?P<artifact>[A-Za-z0-9_.-]+):(?P<version>[^'\"\s)]+)['\"]"
        )
        for match in shorthand_pattern.finditer(content):
            scope = f"gradle/{match.group('config')}"
            cls._add_component(
                components,
                seen,
                warnings,
                f"{match.group('group')}:{match.group('artifact')}",
                match.group("version"),
                scope,
            )

        map_pattern = re.compile(
            r"(?P<config>\w+)\s*\(?\s*group:\s*['\"](?P<group>[^'\"]+)['\"]\s*,\s*name:\s*['\"](?P<artifact>[^'\"]+)['\"]\s*,\s*version:\s*['\"](?P<version>[^'\"]+)['\"]"
        )
        for match in map_pattern.finditer(content):
            scope = f"gradle/{match.group('config')}"
            cls._add_component(
                components,
                seen,
                warnings,
                f"{match.group('group')}:{match.group('artifact')}",
                match.group("version"),
                scope,
            )

        return cls._result(components, warnings, "No Gradle dependencies were found.")

    @classmethod
    def _parse_cargo_toml(cls, content: str) -> dict:
        payload, error = cls._load_toml(content, "Cargo.toml")
        if error:
            return cls._empty_result(error)

        components = []
        warnings = []
        seen = set()
        if isinstance(payload, dict):
            cls._add_cargo_dependency_table(components, seen, warnings, payload.get("dependencies"), "cargo/runtime")
            cls._add_cargo_dependency_table(components, seen, warnings, payload.get("dev-dependencies"), "cargo/development")
            cls._add_cargo_dependency_table(components, seen, warnings, payload.get("build-dependencies"), "cargo/build")
            targets = payload.get("target")
            if isinstance(targets, dict):
                for target_data in targets.values():
                    if isinstance(target_data, dict):
                        cls._add_cargo_dependency_table(
                            components,
                            seen,
                            warnings,
                            target_data.get("dependencies"),
                            "cargo/target",
                        )

        return cls._result(components, warnings, "No Cargo dependencies were found.")

    @classmethod
    def _parse_csproj(cls, content: str) -> dict:
        root, error = cls._load_xml(content, ".csproj")
        if error:
            return cls._empty_result(error)

        components = []
        warnings = []
        seen = set()

        for reference in cls._xml_descendants(root, "PackageReference"):
            package_name = reference.attrib.get("Include") or reference.attrib.get("Update")
            version = reference.attrib.get("Version") or cls._xml_child_text(reference, "Version")
            cls._add_component(components, seen, warnings, package_name, version, "nuget/csproj")

        return cls._result(components, warnings, "No .NET package references were found.")

    @classmethod
    def _parse_composer_json(cls, content: str) -> dict:
        payload, error = cls._load_json(content, "composer.json")
        if error:
            return cls._empty_result(error)
        if not isinstance(payload, dict):
            return cls._empty_result("composer.json must contain a JSON object.")

        components = []
        warnings = []
        seen = set()

        for section, scope in (("require", "composer/runtime"), ("require-dev", "composer/development")):
            dependencies = payload.get(section) or {}
            if not isinstance(dependencies, dict):
                continue
            for package_name, raw_version in dependencies.items():
                if package_name == "php" or package_name.startswith("ext-"):
                    continue
                cls._add_component(components, seen, warnings, package_name, raw_version, scope)

        return cls._result(components, warnings, "No Composer dependencies were found.")

    @classmethod
    def _add_python_requirement_list(cls, components, seen, warnings, requirements, scope: str):
        if not isinstance(requirements, list):
            return
        for requirement in requirements:
            parsed = cls._parse_python_requirement(str(requirement))
            if not parsed:
                warnings.append(f"Skipped unsupported Python requirement '{requirement}'.")
                continue
            package_name, _operator, raw_version = parsed
            cls._add_component(components, seen, warnings, package_name, raw_version, scope)

    @classmethod
    def _add_poetry_dependency_table(cls, components, seen, warnings, dependencies, scope: str):
        if not isinstance(dependencies, dict):
            return
        for package_name, spec in dependencies.items():
            if str(package_name).lower() == "python":
                continue
            if isinstance(spec, dict):
                if spec.get("path") or spec.get("git"):
                    warnings.append(f"Skipped {package_name}: unsupported version spec '{spec}'.")
                    continue
                spec = spec.get("version")
            cls._add_component(components, seen, warnings, package_name, spec, scope)

    @classmethod
    def _add_cargo_dependency_table(cls, components, seen, warnings, dependencies, scope: str):
        if not isinstance(dependencies, dict):
            return
        for package_name, spec in dependencies.items():
            if isinstance(spec, dict):
                if spec.get("path") or spec.get("git"):
                    warnings.append(f"Skipped {package_name}: unsupported version spec '{spec}'.")
                    continue
                spec = spec.get("version")
            cls._add_component(components, seen, warnings, package_name, spec, scope)

    @classmethod
    def _add_component(
        cls,
        components: list,
        seen: set,
        warnings: list,
        package_name,
        raw_version,
        scope: str,
        unsupported_label: str | None = None,
    ):
        package_name = str(package_name or "").strip()
        normalized_version = cls._normalize_version_spec(str(raw_version or "").strip())
        if not package_name:
            return
        if not normalized_version:
            warnings.append(f"Skipped {package_name}: unsupported version spec '{unsupported_label or raw_version}'.")
            return

        dedupe_key = (scope.split("/", 1)[0], package_name.lower())
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        components.append(
            {
                "category": "Package",
                "key": "library",
                "name": package_name,
                "version": normalized_version,
                "scope": scope,
            }
        )

    @staticmethod
    def _empty_result(error: str) -> dict:
        return {"components": [], "warnings": [], "error": error}

    @staticmethod
    def _result(components: list, warnings: list, empty_error: str) -> dict:
        return {
            "components": components,
            "warnings": warnings,
            "error": "" if components else empty_error,
        }

    @staticmethod
    def _load_json(content: str, label: str):
        try:
            return json.loads(content), ""
        except json.JSONDecodeError as exc:
            return None, f"Invalid {label}: {exc.msg}."

    @staticmethod
    def _load_toml(content: str, label: str):
        try:
            return tomllib.loads(content), ""
        except tomllib.TOMLDecodeError as exc:
            return None, f"Invalid {label}: {exc}."

    @staticmethod
    def _load_xml(content: str, label: str):
        try:
            return ET.fromstring(content), ""
        except ET.ParseError as exc:
            return None, f"Invalid {label}: {exc}."

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
    def _strip_go_comment(line: str) -> str:
        return line.split("//", 1)[0]

    @staticmethod
    def _normalize_version_spec(spec: str) -> str:
        value = (spec or "").strip().strip("'\"")
        if not value:
            return ""

        lowered = value.lower()
        if lowered in {"latest", "*"}:
            return ""
        if lowered.startswith(("file:", "git+", "http://", "https://", "github:", "workspace:", "link:", "path:")):
            return ""
        if value.startswith("${") and value.endswith("}"):
            return ""

        # Use the first concrete version from common semver/PEP 440 ranges.
        match = re.search(r"\d+(?:[._-]?\d+)*(?:[a-zA-Z]+\.?\d*)?(?:[-+][A-Za-z0-9_.-]+)?", value)
        if not match:
            return ""
        return match.group(0).lstrip("v")

    @staticmethod
    def _parse_python_requirement(line: str):
        match = re.match(
            r"^([A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)\s*(===|==|~=|>=|<=|>|<|!=)\s*([^;\s,]+)",
            line.strip(),
        )
        if not match:
            return None
        return match.group(1).split("[", 1)[0], match.group(2), match.group(3)

    @staticmethod
    def _split_yarn_descriptors(value: str) -> list[str]:
        parts = []
        current = []
        quote = ""
        for char in value:
            if char in {"'", '"'}:
                quote = "" if quote == char else char
                current.append(char)
            elif char == "," and not quote:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())
        return parts

    @staticmethod
    def _npm_name_from_descriptor(descriptor: str) -> str:
        value = descriptor.strip().strip("'\"")
        if not value or value.startswith("__"):
            return ""
        if value.startswith("@"):
            separator = value.find("@", 1)
            return value[:separator] if separator > 0 else value
        return value.split("@", 1)[0]

    @classmethod
    def _xml_descendants(cls, root, tag_name: str):
        return [element for element in root.iter() if cls._xml_local_name(element.tag) == tag_name]

    @classmethod
    def _xml_child_text(cls, element, tag_name: str) -> str:
        for child in list(element):
            if cls._xml_local_name(child.tag) == tag_name and child.text:
                return child.text.strip()
        return ""

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @classmethod
    def _xml_properties(cls, root) -> dict:
        properties = {}
        for properties_element in cls._xml_descendants(root, "properties"):
            for child in list(properties_element):
                if child.text:
                    properties[cls._xml_local_name(child.tag)] = child.text.strip()
        return properties

    @staticmethod
    def _resolve_property(value: str, properties: dict) -> str:
        value = (value or "").strip()
        match = re.fullmatch(r"\$\{([^}]+)\}", value)
        if match:
            return properties.get(match.group(1), "")
        return value
