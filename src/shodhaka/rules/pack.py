"""Load and validate rule packs.

A rule pack is a YAML file that follows rulepack.schema.json (next to this module). The same
loader serves every standard: DORA, ISO 27001 or a company's own architecture rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).with_name("rulepack.schema.json")


class RulePackError(ValueError):
    """The rule pack is not valid. The message lists every problem found."""


@dataclass(frozen=True)
class Option:
    name: str
    verdict: str  # compliant | gap | not_applicable
    description: str


@dataclass(frozen=True)
class DeciderCheck:
    question: str
    options: tuple[Option, ...]
    topic: str = ""
    scope: str = "section"  # section | document

    def verdict_of(self, option_name: str) -> str:
        for option in self.options:
            if option.name == option_name:
                return option.verdict
        raise KeyError(option_name)

    def option(self, option_name: str) -> Option:
        for option in self.options:
            if option.name == option_name:
                return option
        raise KeyError(option_name)


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    applies_to: tuple[str, ...]
    requirement: str
    fix_hint: str = ""
    decider: DeciderCheck | None = None
    deterministic: str | None = None
    params: dict = field(default_factory=dict)

    @property
    def method(self) -> str:
        return "decider" if self.decider else "code"


@dataclass(frozen=True)
class RulePack:
    pack: str
    version: str
    title: str
    description: str
    rules: tuple[Rule, ...]

    def rules_for(self, kind: str) -> list[Rule]:
        return [rule for rule in self.rules if kind in rule.applies_to]

    def rule(self, rule_id: str) -> Rule:
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        raise KeyError(rule_id)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    """Return every problem with the pack; an empty list means it is valid."""
    validator = jsonschema.Draft202012Validator(_schema())
    def message(error: jsonschema.ValidationError) -> str:
        if error.validator == "oneOf":
            return "a rule needs exactly one of 'decider' or 'deterministic'"
        return error.message

    problems = [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {message(error)}"
        for error in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    ]
    if problems:
        return problems
    seen: set[str] = set()
    for rule in data["rules"]:
        if rule["id"] in seen:
            problems.append(f"rules/{rule['id']}: duplicate rule id")
        seen.add(rule["id"])
        if "decider" in rule:
            verdicts = {opt["verdict"] for opt in rule["decider"]["options"].values()}
            if "gap" not in verdicts or "compliant" not in verdicts:
                problems.append(
                    f"rules/{rule['id']}: decider options need at least one 'gap' and one 'compliant' verdict"
                )
    return problems


def parse(data: dict) -> RulePack:
    problems = validate(data)
    if problems:
        raise RulePackError("invalid rule pack:\n  " + "\n  ".join(problems))
    rules = []
    for raw in data["rules"]:
        decider = None
        if "decider" in raw:
            decider = DeciderCheck(
                topic=raw["decider"].get("topic", "").strip(),
                scope=raw["decider"].get("scope", "section"),
                question=raw["decider"]["question"].strip(),
                options=tuple(
                    Option(name, spec["verdict"], spec["description"].strip())
                    for name, spec in raw["decider"]["options"].items()
                ),
            )
        rules.append(
            Rule(
                id=raw["id"],
                title=raw["title"],
                severity=raw["severity"],
                applies_to=tuple(raw["applies_to"]),
                requirement=" ".join(raw["requirement"].split()),
                fix_hint=raw.get("fix_hint", "").strip(),
                decider=decider,
                deterministic=raw.get("deterministic", {}).get("check"),
                params=raw.get("deterministic", {}).get("params", {}),
            )
        )
    return RulePack(
        pack=data["pack"],
        version=str(data["version"]),
        title=data["title"],
        description=" ".join(data.get("description", "").split()),
        rules=tuple(rules),
    )


def load_pack(path: str | Path) -> RulePack:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulePackError(f"invalid rule pack: not valid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise RulePackError("invalid rule pack: top level must be a mapping")
    return parse(data)


def parse_yaml(text: str) -> dict:
    """YAML text -> raw pack dict, with the same friendly errors as load_pack (not yet validated)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulePackError(f"invalid rule pack: not valid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise RulePackError("invalid rule pack: top level must be a mapping")
    return data


def to_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def compose(general: list[dict], project: list[dict], title: str = "Rules in effect") -> tuple[dict, dict[str, dict]]:
    """Layer rule packs: organisation-wide (general) packs first, then project packs.

    A project rule with the same id as a general rule replaces it (tighten or relax a company rule
    for one project). Two packs in the same layer may not define the same rule id.
    Returns the combined raw pack (valid against the schema) and, per rule id, where it came from:
    {"scope": "organization" | "project", "pack": <pack id>, "overrides": <general pack id> | None}.
    """
    rules: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    for scope, packs in (("organization", general), ("project", project)):
        for pack in packs:
            for rule in pack["rules"]:
                previous = sources.get(rule["id"])
                if previous and previous["scope"] == scope:
                    raise RulePackError(f"rule {rule['id']} is defined in both {previous['pack']} and {pack['pack']} "
                                        f"({scope} rule ids must be unique)")
                rules[rule["id"]] = rule
                sources[rule["id"]] = {"scope": scope, "pack": pack["pack"],
                                       "overrides": previous["pack"] if previous else None}
    if not rules:
        raise RulePackError("no rules: add a general or a project rule pack first")
    used = [p["pack"] for p in general + project]
    combined = {"pack": "effective", "version": "+".join(f"{p['pack']}@{p['version']}" for p in general + project)[:200],
                "title": title, "description": f"Combined from: {', '.join(used)}", "rules": list(rules.values())}
    return combined, sources
