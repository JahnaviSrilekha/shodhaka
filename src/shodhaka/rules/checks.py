"""Deterministic checks: anything that can be decided exactly is decided in code, not by a model.

Each check returns a CheckResult. Evidence never contains the secret value itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from shodhaka.documents.model import Document

SECRET_KEY = re.compile(r"(password|passwd|pwd|secret|api[-_]?key|token|private[-_]?key|credentials?)$", re.I)
PLACEHOLDER = re.compile(r"^\s*(\$\{[^}]+\}|<[^>]+>|\*+|)\s*$")


@dataclass
class CheckResult:
    verdict: str  # compliant | gap | not_applicable
    evidence: list[dict] = field(default_factory=list)  # {"line": int, "text": str}
    note: str = ""


def _flatten(node, prefix: str = "") -> dict[str, object]:
    items: dict[str, object] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            items.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        items[prefix] = node
    return items


def config_documents(doc: Document) -> list[dict[str, object]]:
    """Each YAML document (`---` separates Spring profiles) or the .properties file, as dotted keys."""
    if doc.path.endswith(".properties"):
        entries = {}
        for line in doc.text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "!")) or "=" not in line:
                continue
            key, value = line.split("=", 1)
            entries[key.strip()] = value.strip()
        return [entries]
    try:
        return [_flatten(part) for part in yaml.safe_load_all(doc.text) if isinstance(part, dict)]
    except yaml.YAMLError:
        return []


def config_entries(doc: Document) -> dict[str, object]:
    """All documents merged; the first (default profile) wins when a profile repeats a key."""
    merged: dict[str, object] = {}
    for part in config_documents(doc):
        for key, value in part.items():
            merged.setdefault(key, value)
    return merged


def _line_of(doc: Document, key: str) -> int:
    """Line where `key` is assigned: `a.b.c=` in .properties or flat YAML, else the nested YAML path
    a: / b: / c: (so `spring.mail.password` is not confused with an earlier `mongodb.password`)."""
    lines = doc.text.splitlines()
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith((f"{key}=", f"{key} =", f"{key}:")):
            return number
    start, parent_indent, found = 0, -1, 0
    for part in key.split("."):
        found = 0
        for index in range(start, len(lines)):
            line = lines[index]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= parent_indent:
                break  # left the parent block
            if stripped.startswith(f"{part}:"):
                found, start, parent_indent = index + 1, index + 1, indent
                break
        if not found:
            break
    if found:
        return found
    leaf = key.split(".")[-1]
    return next((n for n, line in enumerate(lines, start=1) if line.strip().startswith(f"{leaf}:")), 0)


def secret_scan(doc: Document, params: dict | None = None) -> CheckResult:
    hits = []
    seen = set()
    for key, value in ((k, v) for part in config_documents(doc) for k, v in part.items()):  # every profile
        if (key, str(value)) in seen:
            continue
        seen.add((key, str(value)))
        leaf = key.split(".")[-1]
        if SECRET_KEY.search(leaf) and value is not None and not PLACEHOLDER.match(str(value)):
            hits.append({"line": _line_of(doc, key), "text": f"{key} = <literal value redacted>"})
    if hits:
        return CheckResult("gap", hits, f"{len(hits)} literal secret value(s) in the file")
    return CheckResult("compliant", note="no literal secret values; secrets come from placeholders")


def health_endpoint(doc: Document, params: dict | None = None) -> CheckResult:
    entries = config_entries(doc)
    if not any(str(k).startswith("spring.") for k in entries):
        return CheckResult("not_applicable", note="not a Spring Boot configuration")
    # Spring Boot 2+ exposes /actuator/health over HTTP by default, so only an explicit setting can hide it.
    def listed(key: str) -> tuple[str | None, list[str]]:
        value = entries.get(key)
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        return value, [] if value is None else [v.strip() for v in str(value).split(",")]

    exclude, excluded = listed("management.endpoints.web.exposure.exclude")
    if "health" in excluded or "*" in excluded:
        return CheckResult("gap", [{"line": _line_of(doc, "management.endpoints.web.exposure.exclude"),
                                    "text": f"exposure.exclude = {exclude}"}], "health endpoint is excluded")
    for key in ("management.endpoint.health.enabled", "management.endpoint.health.access"):
        if key in entries and str(entries[key]).lower() in ("false", "none"):
            return CheckResult("gap", [{"line": _line_of(doc, key), "text": f"{key} = {entries[key]}"}], "health endpoint is disabled")
    include, included = listed("management.endpoints.web.exposure.include")
    if include is None:
        return CheckResult("compliant", note="exposure not set: Spring Boot 2+ exposes /actuator/health by default "
                                             "when spring-boot-starter-actuator is on the classpath (check the build file)")
    line = _line_of(doc, "management.endpoints.web.exposure.include")
    if "health" in included or "*" in included:
        return CheckResult("compliant", [{"line": line, "text": f"exposure.include = {include}"}])
    return CheckResult("gap", [{"line": line, "text": f"exposure.include = {include}"}],
                       "exposure.include replaces the default list and leaves out health")


FROM_LINE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.I)


def pinned_base_image(doc: Document, params: dict | None = None) -> CheckResult:
    unpinned, pinned, stages = [], [], set()
    for number, line in enumerate(doc.text.splitlines(), start=1):
        match = FROM_LINE.match(line)
        if not match:
            continue
        image = match.group(1)
        alias = re.search(r"\s+AS\s+(\S+)\s*$", line, re.I)
        is_earlier_stage = image.lower() in stages
        if alias:
            stages.add(alias.group(1).lower())
        if is_earlier_stage:
            continue  # FROM <earlier build stage>: not an image from a registry
        if image.lower() == "scratch" or "@sha256:" in image:
            pinned.append(number)
            continue
        name_part = image.rsplit("/", 1)[-1]
        tag = name_part.split(":", 1)[1] if ":" in name_part else ""
        if not tag or tag == "latest":
            unpinned.append({"line": number, "text": line.strip()})
        else:
            pinned.append(number)
    if unpinned:
        return CheckResult("gap", unpinned, "base image uses the latest tag or no tag")
    if pinned:
        return CheckResult("compliant", note="all base images are pinned")
    return CheckResult("not_applicable", note="no FROM line found")


CHECKS = {
    "secret_scan": secret_scan,
    "health_endpoint": health_endpoint,
    "pinned_base_image": pinned_base_image,
}
