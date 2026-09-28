import re
from pathlib import Path

import yaml

from .models import SourceFile


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    result = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(flatten(value, name))
        elif value is not None:
            result[name] = ",".join(map(str, value)) if isinstance(value, list) else str(value)
    return result


def properties(text: str) -> dict[str, str]:
    text = re.sub(r"(?<!\\)\\\r?\n\s*", "", text)
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        match = re.match(r"([^\s=:]+)\s*(?:[=:]\s*|\s+)(.*)$", line)
        if match:
            result[match[1]] = re.sub(r"\\u([\da-fA-F]{4})|\\(.)",
                                     lambda m: chr(int(m[1], 16)) if m[1] else
                                     {"n": "\n", "r": "\r", "t": "\t"}.get(m[2], m[2]), match[2])
    return result


class Configuration:
    def __init__(self, values: dict[str, str]):
        self.values = values

    def resolve(self, value: str | None) -> str | None:
        if value is None:
            return None
        seen = set()
        for _ in range(30):
            if "${" not in value:
                return value.strip() or None
            if value in seen:
                return None
            seen.add(value)
            unresolved = False

            def replace(match):
                nonlocal unresolved
                key, separator, default = match[1].partition(":")
                if key in self.values:
                    return self.values[key]
                if separator:
                    return default
                unresolved = True
                return match[0]

            value = re.sub(r"\$\{([^{}]*)\}", replace, value)
            if unresolved:
                return None
        return None


def load_configurations(files: list[SourceFile], profile: str | None) -> dict[Path, Configuration]:
    configurations = {}
    for root in {source.main_root for source in files}:
        candidates = [source for source in files if source.main_root == root
                      and source.path.suffix in {".properties", ".yaml", ".yml"}
                      and re.fullmatch(r"application(?:-[\w,-]+)?", source.path.stem)]
        # properties prevalece sobre YAML; resources/config prevalece sobre resources.
        candidates.sort(key=lambda source: (len(source.path.parts),
                                             source.path.suffix == ".properties", str(source.path)))
        documents = []
        for source in candidates:
            if source.path.suffix == ".properties":
                entries = [properties(source.text)]
            else:
                entries = [flatten(doc) for doc in yaml.safe_load_all(source.text) if isinstance(doc, dict)]
            documents.extend((source.path.stem, entry) for entry in entries)
        values = {}
        for stem, entry in documents:
            if stem == "application" and not entry.get("spring.config.activate.on-profile") and not entry.get("spring.profiles"):
                values.update(entry)
        selected = profile or Configuration(values).resolve(values.get("spring.profiles.active"))
        selected = selected or Configuration(values).resolve(values.get("spring.profiles.default")) or "default"
        profiles = [item.strip() for item in selected.split(",") if item.strip()]
        for active in profiles:
            for stem, entry in documents:
                condition = entry.get("spring.config.activate.on-profile", entry.get("spring.profiles", ""))
                matches = active in [item.strip() for item in condition.split(",")]
                if (stem == "application" and matches) or (stem == f"application-{active}" and (not condition or matches)):
                    values.update(entry)
        configurations[root] = Configuration(values)
    return configurations
