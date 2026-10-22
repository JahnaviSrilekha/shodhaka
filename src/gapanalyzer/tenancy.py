"""Organisations, projects and their rule packs, kept as plain files (no database, no login).

    <workspace>/orgs/<org>/org.json
    <workspace>/orgs/<org>/packs/<pack>.yaml                         general rule packs (whole organisation)
    <workspace>/orgs/<org>/projects/<project>/project.json
    <workspace>/orgs/<org>/projects/<project>/packs/<pack>.yaml      project-specific rule packs
    <workspace>/orgs/<org>/projects/<project>/analyses/<analysis>/   uploads, report, reviews, rule snapshot

Isolation is by path: every lookup goes through an organisation and a project, ids are checked
against a strict pattern, so one project's documents, reports and rules never mix with another's.
Without login anyone at the machine can switch organisations: it separates work, it is not access control.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from .rulepack import RulePackError, compose, parse_yaml, to_yaml, validate

ID = re.compile(r"[a-f0-9]{12}")
PACK_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,63}")


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Workspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root) / "orgs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    # ---- json helpers -------------------------------------------------------------------------
    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: Any) -> None:
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(path)

    # ---- organisations ------------------------------------------------------------------------
    def org_dir(self, org_id: str) -> Path:
        folder = self.root / org_id
        if not ID.fullmatch(org_id) or not (folder / "org.json").exists():
            raise NotFound("organization not found")
        return folder

    def list_orgs(self) -> list[dict]:
        orgs = [self._read(p / "org.json") for p in self.root.iterdir() if (p / "org.json").exists()]
        for org in orgs:
            org["projects"] = sum(1 for _ in (self.root / org["id"] / "projects").glob("*/project.json"))
            org["general_packs"] = len(list((self.root / org["id"] / "packs").glob("*.yaml")))
        return sorted(orgs, key=lambda o: o["name"].lower())

    def create_org(self, name: str, description: str = "") -> dict:
        name = name.strip()
        if not name:
            raise Conflict("the organization needs a name")
        with self.lock:
            if any(o["name"].lower() == name.lower() for o in self.list_orgs()):
                raise Conflict(f"an organization called {name} already exists")
            org = {"id": uuid.uuid4().hex[:12], "name": name, "description": description.strip(), "created_at": _now()}
            self._write(self.root / org["id"] / "org.json", org)
        return org

    def get_org(self, org_id: str) -> dict:
        return self._read(self.org_dir(org_id) / "org.json")

    # ---- projects -----------------------------------------------------------------------------
    def project_dir(self, org_id: str, project_id: str) -> Path:
        folder = self.org_dir(org_id) / "projects" / project_id
        if not ID.fullmatch(project_id) or not (folder / "project.json").exists():
            raise NotFound("project not found")
        return folder

    def list_projects(self, org_id: str) -> list[dict]:
        folder = self.org_dir(org_id) / "projects"
        projects = [self._read(p) for p in folder.glob("*/project.json")]
        for p in projects:
            p["analyses"] = sum(1 for _ in (folder / p["id"] / "analyses").glob("*/meta.json"))
            p["project_packs"] = len(list((folder / p["id"] / "packs").glob("*.yaml")))
        return sorted(projects, key=lambda p: p["name"].lower())

    def create_project(self, org_id: str, name: str, description: str = "") -> dict:
        name = name.strip()
        if not name:
            raise Conflict("the project needs a name")
        with self.lock:
            if any(p["name"].lower() == name.lower() for p in self.list_projects(org_id)):
                raise Conflict(f"a project called {name} already exists in this organization")
            project = {"id": uuid.uuid4().hex[:12], "org": org_id, "name": name, "description": description.strip(),
                       "excluded_general_packs": [], "created_at": _now()}
            self._write(self.org_dir(org_id) / "projects" / project["id"] / "project.json", project)
        return project

    def get_project(self, org_id: str, project_id: str) -> dict:
        return self._read(self.project_dir(org_id, project_id) / "project.json")

    def update_project(self, org_id: str, project_id: str, **changes: Any) -> dict:
        with self.lock:
            project = self.get_project(org_id, project_id)
            if "excluded_general_packs" in changes:
                known = {p["pack"] for p in self.list_packs(org_id)}
                unknown = set(changes["excluded_general_packs"]) - known
                if unknown:
                    raise Conflict(f"unknown general packs: {', '.join(sorted(unknown))}")
                project["excluded_general_packs"] = sorted(set(changes["excluded_general_packs"]))
            for key in ("name", "description"):
                if changes.get(key) is not None:
                    project[key] = changes[key].strip()
            self._write(self.project_dir(org_id, project_id) / "project.json", project)
        return project

    def analyses_dir(self, org_id: str, project_id: str) -> Path:
        folder = self.project_dir(org_id, project_id) / "analyses"
        folder.mkdir(exist_ok=True)
        return folder

    # ---- rule packs (scope: general = whole organisation, or one project) ----------------------
    def packs_dir(self, org_id: str, project_id: str | None = None) -> Path:
        base = self.project_dir(org_id, project_id) if project_id else self.org_dir(org_id)
        folder = base / "packs"
        folder.mkdir(exist_ok=True)
        return folder

    def _pack_path(self, org_id: str, project_id: str | None, pack_id: str) -> Path:
        if not PACK_ID.fullmatch(pack_id):
            raise NotFound("rule pack not found")
        return self.packs_dir(org_id, project_id) / f"{pack_id}.yaml"

    def list_packs(self, org_id: str, project_id: str | None = None) -> list[dict]:
        """Raw pack dicts of one scope (broken files are reported, not hidden)."""
        packs = []
        for path in sorted(self.packs_dir(org_id, project_id).glob("*.yaml")):
            try:
                packs.append(parse_yaml(path.read_text(encoding="utf-8")))
            except RulePackError as exc:
                packs.append({"pack": path.stem, "title": path.stem, "version": "?", "rules": [], "error": str(exc)})
        return packs

    def get_pack(self, org_id: str, project_id: str | None, pack_id: str) -> tuple[dict, str]:
        path = self._pack_path(org_id, project_id, pack_id)
        if not path.exists():
            raise NotFound("rule pack not found")
        text = path.read_text(encoding="utf-8")
        return parse_yaml(text), text

    def save_pack(self, org_id: str, project_id: str | None, data: dict, text: str | None = None,
                  replace: str | None = None) -> dict:
        """Validate and store a pack. `replace` is the id being edited (None = create).
        Keeps the author's YAML (comments included) when it was uploaded as text."""
        problems = validate(data)
        if problems:
            raise RulePackError("invalid rule pack:\n  " + "\n  ".join(problems))
        pack_id = data["pack"]
        if replace is not None and replace != pack_id:
            raise Conflict("the pack id cannot change; create a new pack instead")
        with self.lock:
            path = self._pack_path(org_id, project_id, pack_id)
            if replace is None and path.exists():
                raise Conflict(f"a rule pack with id {pack_id} already exists here")
            if replace is not None and not path.exists():
                raise NotFound("rule pack not found")
            # rule ids must be unique within one layer (organisation or project)
            mine = {r["id"] for r in data["rules"]}
            for other in self.list_packs(org_id, project_id):
                if other["pack"] != pack_id:
                    clash = mine & {r["id"] for r in other.get("rules", [])}
                    if clash:
                        raise Conflict(f"rule {', '.join(sorted(clash))} already exists in pack {other['pack']} "
                                       f"at this level; use another id")
            path.write_text(text if text is not None else to_yaml(data), encoding="utf-8")
        return data

    def delete_pack(self, org_id: str, project_id: str | None, pack_id: str) -> None:
        path = self._pack_path(org_id, project_id, pack_id)
        if not path.exists():
            raise NotFound("rule pack not found")
        path.unlink()  # analyses keep their own rule snapshot, so past reports stay reproducible

    # ---- rules in effect for a project ---------------------------------------------------------
    def effective(self, org_id: str, project_id: str) -> tuple[dict, dict[str, dict], list[str]]:
        project = self.get_project(org_id, project_id)
        excluded = set(project.get("excluded_general_packs", []))
        general = [p for p in self.list_packs(org_id) if p["pack"] not in excluded and "error" not in p]
        local = [p for p in self.list_packs(org_id, project_id) if "error" not in p]
        combined, sources = compose(general, local, title=f"{self.get_org(org_id)['name']} / {project['name']}")
        return combined, sources, [p["pack"] for p in general + local]
