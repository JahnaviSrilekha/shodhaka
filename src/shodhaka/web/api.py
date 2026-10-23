"""HTTP API behind the review UI (ui/). Local only: bind it to 127.0.0.1.

    shodhaka serve --threshold 0.75        # then open http://127.0.0.1:8000

Everything is scoped: organisation -> project -> analysis. An organisation has general rule packs
that apply to all its projects; a project can switch general packs off and add its own packs,
whose rules override a general rule with the same id. Each analysis stores a snapshot of the
rules it ran with, so later edits to a pack never change an existing report.

Flow inside a project: upload documents -> Decider analyses them in the background -> a person
approves / rejects every finding, edits a document and re-checks it -> decisions export as
expected.json for `shodhaka eval`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shodhaka.analysis.engine import DEFAULT_THRESHOLD, DESIGN_SET, MODES, analyze
from shodhaka.analysis.fixes import FixWriter, add_fixes
from shodhaka.analysis.recommend import recommend
from shodhaka.decider import Decider, DeciderUnavailable
from shodhaka.documents.model import classify, document_from_text, load_document
from shodhaka.documents.sanitize import clean, remove_unsafe
from shodhaka.rules.pack import RulePackError, compose, parse, parse_yaml, to_yaml, validate
from shodhaka.web.workspace import ID, Conflict, NotFound, Workspace

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILES = 50
TOOL_VERDICT = {"gap": "gap", "covered": "compliant", "not_applicable": "not_applicable"}
CHECKS = ["secret_scan", "health_endpoint", "pinned_base_image"]


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected", "resolved"]  # resolved = a needs_review finding decided by a person
    verdict: Literal["gap", "compliant", "not_applicable"] | None = None
    note: str = Field(default="", max_length=2000)
    fix: str | None = Field(default=None, max_length=4000)


class TextIn(BaseModel):
    text: str = Field(max_length=500_000)


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    excluded_general_packs: list[str] | None = None


class PackIn(BaseModel):
    """One of: `yaml` (uploaded or typed text), `pack` (from the form editor), `template` (a built-in pack id)."""
    yaml: str | None = Field(default=None, max_length=500_000)
    pack: dict[str, Any] | None = None
    template: str | None = None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _safe_name(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    return base or "document"


class Analyses:
    """The analyses of one project: one folder each. Writes share the workspace lock."""

    def __init__(self, root: Path, lock: threading.RLock) -> None:
        self.root, self.lock = root, lock

    def folder(self, analysis_id: str) -> Path:
        folder = self.root / analysis_id
        if not ID.fullmatch(analysis_id) or not (folder / "meta.json").exists():
            raise NotFound("analysis not found")
        return folder

    def read(self, analysis_id: str, name: str, default: Any = None) -> Any:
        path = self.folder(analysis_id) / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def write(self, analysis_id: str, name: str, data: Any) -> None:
        with self.lock:
            path = self.root / analysis_id / name
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(path)

    def text_path(self, analysis_id: str, document: str) -> Path:
        folder = self.folder(analysis_id)
        target = (folder / "text" / (document + ".txt")).resolve()
        if not target.is_relative_to((folder / "text").resolve()):
            raise NotFound("document not found")
        return target


def create_app(workspace: str | Path, pack_dir: str | Path,
               decider_factory: Callable[[], Decider],
               threshold: float = DEFAULT_THRESHOLD,
               bedrock: dict[str, str] | None = None,
               ui_dist: str | Path | None = None) -> FastAPI:
    ws = Workspace(workspace)
    templates_dir = Path(pack_dir)
    run_lock = threading.Lock()  # one analysis at a time: there is one local Decider
    app = FastAPI(title="Shodhaka", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.exception_handler(NotFound)
    def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    def _conflict(_: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(RulePackError)
    def _invalid_pack(_: Request, exc: RulePackError) -> JSONResponse:
        lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
        return JSONResponse({"detail": {"message": lines[0], "problems": lines[1:]}}, status_code=422)

    def analyses(org_id: str, project_id: str) -> Analyses:
        return Analyses(ws.analyses_dir(org_id, project_id), ws.lock)

    def templates() -> dict[str, tuple[dict, str]]:
        found = {}
        for path in sorted(templates_dir.glob("*.y*ml")):
            try:
                text = path.read_text(encoding="utf-8")
                data = parse_yaml(text)
            except RulePackError:
                continue
            if not validate(data):
                found[data["pack"]] = (data, text)
        return found

    # ---- background analysis -------------------------------------------------------------------
    def run_analysis(store: Analyses, analysis_id: str, only: str | None = None) -> None:
        def update(**changes: Any) -> None:
            with store.lock:
                meta = store.read(analysis_id, "meta.json")
                meta.update(changes)
                store.write(analysis_id, "meta.json", meta)

        with run_lock:
            meta = store.read(analysis_id, "meta.json")
            try:
                folder = store.folder(analysis_id)
                pack = parse(parse_yaml((folder / "rules.yaml").read_text(encoding="utf-8")))  # the snapshot
                sources = store.read(analysis_id, "rule_sources.json", {})
                mode = meta.get("mode", "per-document")
                # a design set is judged as a whole, so changing one of its documents re-checks all of them
                scope_only = None if mode == "design-set" else only
                decider = decider_factory()
                # Cleaning comes first: unsafe language is removed (Decider, locally) before any
                # rule check reads the text. Secrets, personal data and instructions to the AI were
                # already removed by patterns when the file arrived.
                checked = dict(meta.get("unsafe_checked", {}))
                pending = [p for p in meta["documents"] if scope_only in (None, p) and classify(Path(p)) == "adr"
                           and checked.get(p) != _digest(store.text_path(analysis_id, p).read_text(encoding="utf-8"))]
                if pending:
                    update(status="cleaning", progress={"done": 0, "total": len(pending), "current": None})
                    found = []
                    for i, path in enumerate(pending):
                        update(progress={"done": i, "total": len(pending), "current": path})
                        tp = store.text_path(analysis_id, path)
                        doc = document_from_text(path, tp.read_text(encoding="utf-8"))
                        text, removed = remove_unsafe(doc, decider)
                        if removed:
                            tp.write_text(text, encoding="utf-8")
                            found += [{"document": path, **r.to_dict()} for r in removed]
                        checked[path] = _digest(text)
                    with store.lock:
                        if found:
                            store.write(analysis_id, "removals.json", store.read(analysis_id, "removals.json", []) + found)
                        update(unsafe_checked=checked)
                docs = []
                for path in meta["documents"]:
                    if scope_only in (None, path):
                        doc = document_from_text(path, store.text_path(analysis_id, path).read_text(encoding="utf-8"))
                        if doc is not None:
                            docs.append(doc)
                update(status="running", progress={"done": 0, "total": len(docs), "current": None})
                result = analyze(pack, docs, decider, threshold=meta["threshold"], mode=mode,
                                 progress=lambda done, total, path: update(
                                     progress={"done": done, "total": total, "current": path}))
                writer = FixWriter(decider, **bedrock) if (bedrock and meta.get("bedrock")) else None
                result = add_fixes(result, pack, writer)
                for finding in result["findings"]:
                    finding["rule_source"] = sources.get(finding["rule_id"])
                with store.lock:
                    report = store.read(analysis_id, "report.json")
                    if scope_only is not None and report is not None:
                        result = _merge(report, result, only)
                    elif only is not None and report is not None:  # design set re-checked as a whole
                        result["rechecks"] = report.get("rechecks", []) + [{"document": only, "at": _now(), "decider": result.get("decider", {})}]
                    store.write(analysis_id, "report.json", result)
                    if only is not None:  # the text changed: earlier decisions on it must be looked at again
                        reviews = store.read(analysis_id, "reviews.json", {})
                        for review in reviews.values():
                            if review["document"] in (only, DESIGN_SET):
                                review["stale"] = True
                        store.write(analysis_id, "reviews.json", reviews)
                    edited = [d for d in meta.get("edited", []) if d != only] if only else []
                update(status="done", error=None, edited=edited, finished_at=_now(),
                       progress={"done": len(docs), "total": len(docs), "current": None})
            except DeciderUnavailable as exc:
                update(status="failed", error=f"Decider is not reachable: {exc}")
            except Exception as exc:  # noqa: BLE001 (shown to the reviewer, not swallowed)
                update(status="failed", error=f"{type(exc).__name__}: {exc}")

    def start(store: Analyses, analysis_id: str, only: str | None = None) -> None:
        threading.Thread(target=run_analysis, args=(store, analysis_id, only), daemon=True).start()

    # ---- server ---------------------------------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        decider = decider_factory()
        try:
            info = decider.health() if hasattr(decider, "health") else {"checkpoint": "scripted"}
            return {"decider": "up", "checkpoint": info.get("checkpoint"), "bedrock": bool(bedrock),
                    "default_threshold": threshold}
        except DeciderUnavailable as exc:
            return {"decider": "down", "error": str(exc), "bedrock": bool(bedrock), "default_threshold": threshold}

    @app.get("/api/templates")
    def list_templates() -> list[dict[str, Any]]:
        return [_pack_summary(data) for data, _ in templates().values()]

    @app.post("/api/packs/validate")
    def validate_pack(body: PackIn) -> dict[str, Any]:
        """Form <-> YAML round trip for the editor, without saving anything."""
        try:
            data = parse_yaml(body.yaml) if body.yaml is not None else (body.pack or {})
        except RulePackError as exc:
            return {"valid": False, "problems": [str(exc)], "pack": None, "yaml": body.yaml}
        problems = validate(data)
        return {"valid": not problems, "problems": problems, "pack": data,
                "yaml": body.yaml if body.yaml is not None else to_yaml(data), "checks": CHECKS}

    # ---- organisations and projects ------------------------------------------------------------
    @app.get("/api/orgs")
    def list_orgs() -> list[dict]:
        return ws.list_orgs()

    @app.post("/api/orgs", status_code=201)
    def create_org(body: NameIn) -> dict:
        return ws.create_org(body.name, body.description)

    @app.get("/api/orgs/{org_id}")
    def get_org(org_id: str) -> dict:
        return {**ws.get_org(org_id), "projects": ws.list_projects(org_id),
                "general_packs": [_pack_summary(p) for p in ws.list_packs(org_id)]}

    @app.post("/api/orgs/{org_id}/projects", status_code=201)
    def create_project(org_id: str, body: NameIn) -> dict:
        return ws.create_project(org_id, body.name, body.description)

    @app.get("/api/orgs/{org_id}/projects/{project_id}")
    def get_project(org_id: str, project_id: str) -> dict:
        project = ws.get_project(org_id, project_id)
        general = [_pack_summary(p) | {"applied": p["pack"] not in project["excluded_general_packs"]}
                   for p in ws.list_packs(org_id)]
        try:
            combined, sources, used = ws.effective(org_id, project_id)
            rules = [_rule_summary(r) | sources[r["id"]] for r in combined["rules"]]
            problem = None
        except RulePackError as exc:
            rules, used, problem = [], [], str(exc)
        return {**project, "org_name": ws.get_org(org_id)["name"], "general_packs": general,
                "project_packs": [_pack_summary(p) for p in ws.list_packs(org_id, project_id)],
                "rules": rules, "packs_in_effect": used, "rules_problem": problem}

    @app.patch("/api/orgs/{org_id}/projects/{project_id}")
    def patch_project(org_id: str, project_id: str, body: ProjectPatch) -> dict:
        ws.update_project(org_id, project_id, **body.model_dump(exclude_none=True))
        return get_project(org_id, project_id)

    # ---- rule packs: the same operations for the organisation (general) and for one project -----
    def _get_pack(org_id: str, project_id: str | None, pack_id: str) -> dict:
        data, text = ws.get_pack(org_id, project_id, pack_id)
        return {"pack": data, "yaml": text, "checks": CHECKS}

    def _save_pack(org_id: str, project_id: str | None, body: PackIn, replace: str | None = None) -> dict:
        data, text = _incoming(body)
        ws.save_pack(org_id, project_id, data, text, replace=replace)
        return _pack_summary(data)

    @app.get("/api/orgs/{org_id}/packs/{pack_id}")
    def get_general_pack(org_id: str, pack_id: str) -> dict:
        return _get_pack(org_id, None, pack_id)

    @app.post("/api/orgs/{org_id}/packs", status_code=201)
    def create_general_pack(org_id: str, body: PackIn) -> dict:
        return _save_pack(org_id, None, body)

    @app.put("/api/orgs/{org_id}/packs/{pack_id}")
    def update_general_pack(org_id: str, pack_id: str, body: PackIn) -> dict:
        return _save_pack(org_id, None, body, replace=pack_id)

    @app.delete("/api/orgs/{org_id}/packs/{pack_id}", status_code=204)
    def delete_general_pack(org_id: str, pack_id: str) -> Response:
        ws.delete_pack(org_id, None, pack_id)
        return Response(status_code=204)

    @app.get("/api/orgs/{org_id}/projects/{project_id}/packs/{pack_id}")
    def get_project_pack(org_id: str, project_id: str, pack_id: str) -> dict:
        return _get_pack(org_id, project_id, pack_id)

    @app.post("/api/orgs/{org_id}/projects/{project_id}/packs", status_code=201)
    def create_project_pack(org_id: str, project_id: str, body: PackIn) -> dict:
        return _save_pack(org_id, project_id, body)

    @app.put("/api/orgs/{org_id}/projects/{project_id}/packs/{pack_id}")
    def update_project_pack(org_id: str, project_id: str, pack_id: str, body: PackIn) -> dict:
        return _save_pack(org_id, project_id, body, replace=pack_id)

    @app.delete("/api/orgs/{org_id}/projects/{project_id}/packs/{pack_id}", status_code=204)
    def delete_project_pack(org_id: str, project_id: str, pack_id: str) -> Response:
        ws.delete_pack(org_id, project_id, pack_id)
        return Response(status_code=204)

    def _incoming(body: PackIn) -> tuple[dict, str | None]:
        if body.template is not None:
            found = templates().get(body.template)
            if found is None:
                raise NotFound("template not found")
            return found
        if body.yaml is not None:
            return parse_yaml(body.yaml), body.yaml
        if body.pack is not None:
            return body.pack, None
        raise Conflict("send yaml, pack or template")

    # ---- which rule packs fit: candidates, recommendation, per-analysis selection ---------------
    def candidates(org_id: str, project_id: str) -> list[dict]:
        """Every pack a project could use, each with a ref ("project:<id>", "org:<id>", "template:<id>")."""
        project = ws.get_project(org_id, project_id)
        out = []
        for p in ws.list_packs(org_id, project_id):
            if "error" not in p:
                out.append({"ref": f"project:{p['pack']}", "source": "project", "in_effect": True, "raw": p})
        org_ids = set()
        for p in ws.list_packs(org_id):
            if "error" not in p:
                org_ids.add(p["pack"])
                applied = p["pack"] not in project["excluded_general_packs"]
                out.append({"ref": f"org:{p['pack']}", "source": "organization" if applied else "organization-off",
                            "in_effect": applied, "raw": p})
        for pid, (data, _) in templates().items():
            if pid not in org_ids:
                out.append({"ref": f"template:{pid}", "source": "template", "in_effect": False, "raw": data})
        return out

    def _candidate_public(c: dict) -> dict:
        return {"ref": c["ref"], "source": c["source"], "in_effect": c["in_effect"], **_pack_summary(c["raw"])}

    def compose_selection(org_id: str, project_id: str, refs: list[str]) -> tuple[dict, dict, list[str]]:
        """Rules for an analysis from the packs the person ticked: organization packs and templates form
        the general layer, project packs the project layer (project rules still override)."""
        by_ref = {c["ref"]: c for c in candidates(org_id, project_id)}
        unknown = [r for r in refs if r not in by_ref]
        if unknown:
            raise Conflict(f"unknown rule packs: {', '.join(unknown)}")
        chosen = [by_ref[r] for r in refs]
        general = [c["raw"] for c in chosen if not c["ref"].startswith("project:")]
        local = [c["raw"] for c in chosen if c["ref"].startswith("project:")]
        project = ws.get_project(org_id, project_id)
        combined, sources = compose(general, local, title=f"{ws.get_org(org_id)['name']} / {project['name']}")
        for c in chosen:  # say where a template came from
            if c["ref"].startswith("template:"):
                for rule_id, src in sources.items():
                    if src["pack"] == c["raw"]["pack"] and src["scope"] == "organization":
                        src["scope"] = "template"
        return combined, sources, [c["raw"]["pack"] for c in chosen]

    @app.get("/api/orgs/{org_id}/projects/{project_id}/candidates")
    def list_candidates(org_id: str, project_id: str) -> list[dict]:
        return [_candidate_public(c) for c in candidates(org_id, project_id)]

    @app.post("/api/orgs/{org_id}/projects/{project_id}/recommend")
    async def recommend_packs(org_id: str, project_id: str, files: list[UploadFile] = File(...)) -> dict[str, Any]:
        """Read-only: suggest packs for these files. Nothing is stored."""
        cands = candidates(org_id, project_id)
        docs = []
        with tempfile.TemporaryDirectory() as tmp:
            for upload in files[:MAX_FILES]:
                name = _safe_name(upload.filename or "document")
                data = await upload.read(MAX_UPLOAD_BYTES + 1)
                if len(data) > MAX_UPLOAD_BYTES or classify(Path(name)) is None:
                    continue
                (Path(tmp) / name).write_bytes(data)
                doc = load_document(Path(tmp) / name, Path(tmp))
                if doc is not None:  # Decider only ever sees the cleaned text
                    docs.append(document_from_text(doc.path, clean(doc.text, doc.kind)[0]))
        keyed = [{"id": f"p{i}", "title": c["raw"]["title"], "description": c["raw"].get("description", ""),
                  "rules": _pack_summary(c["raw"])["rules"]} for i, c in enumerate(cands)]
        refs = {f"p{i}": c["ref"] for i, c in enumerate(cands)}
        try:
            result = recommend(docs, keyed, decider_factory())
        except DeciderUnavailable as exc:
            raise HTTPException(503, f"Decider is not reachable, choose the rule packs yourself ({exc})")
        for item in result["documents"]:
            item["pick"] = refs.get(item["pick"])
        for item in result["packs"]:
            item["ref"] = refs[item.pop("id")]
        result["recommended"] = [refs[k] for k in result["recommended"]]
        result["candidates"] = [_candidate_public(c) for c in cands]
        return result

    # ---- analyses inside one project -----------------------------------------------------------
    project_api = APIRouter(prefix="/api/orgs/{org_id}/projects/{project_id}")

    @project_api.get("/analyses")
    def list_analyses(org_id: str, project_id: str) -> list[dict[str, Any]]:
        store = analyses(org_id, project_id)
        items = []
        for folder in store.root.iterdir():
            if (folder / "meta.json").exists():
                meta = store.read(folder.name, "meta.json")
                report = store.read(folder.name, "report.json")
                reviews = store.read(folder.name, "reviews.json", {})
                items.append({**_public(meta), "summary": report["summary"] if report else None,
                              "findings": len(report["findings"]) if report else 0, "reviewed": len(reviews)})
        return sorted(items, key=lambda m: m["created_at"], reverse=True)

    @project_api.post("/analyses", status_code=201)
    async def create_analysis(org_id: str, project_id: str, files: list[UploadFile] = File(...),
                              threshold: float = Form(threshold), use_bedrock: bool = Form(False),
                              mode: str = Form("per-document"), packs: str = Form("")) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        refs = [r.strip() for r in packs.split(",") if r.strip()]
        # the packs ticked for this analysis, or else the project's rules in effect
        combined, sources, used = (compose_selection(org_id, project_id, refs) if refs
                                   else ws.effective(org_id, project_id))
        if not 0.5 <= threshold <= 0.99:
            raise HTTPException(400, "threshold must be between 0.5 and 0.99")
        if mode not in MODES:
            raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
        if not files or len(files) > MAX_FILES:
            raise HTTPException(400, f"upload between 1 and {MAX_FILES} files")
        analysis_id = uuid.uuid4().hex[:12]
        folder = store.root / analysis_id
        (folder / "docs").mkdir(parents=True)
        documents, skipped, removals = [], [], []
        for upload in files:
            name = _safe_name(upload.filename or "document")
            data = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                skipped.append({"file": name, "reason": "larger than 10 MB"})
                continue
            if classify(Path(name)) is None:
                skipped.append({"file": name, "reason": "unsupported type (use .md .pdf .docx .yml .yaml .properties Dockerfile)"})
                continue
            while name in documents:
                name = f"{Path(name).stem}-1{Path(name).suffix}"
            (folder / "docs" / name).write_bytes(data)
            doc = load_document(folder / "docs" / name, folder / "docs")
            if doc is None:
                skipped.append({"file": name, "reason": "could not extract text (scanned PDF? missing reader?)"})
                continue
            # Clean right away: only the cleaned text is ever stored for analysis. The original file
            # stays in docs/ on this machine; no endpoint serves it and nothing analyses it.
            cleaned, removed = clean(doc.text, doc.kind)
            removals += [{"document": name, **r.to_dict()} for r in removed]
            text_path = folder / "text" / (name + ".txt")
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(cleaned, encoding="utf-8")
            documents.append(name)
        if not documents:
            for path in sorted(folder.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            folder.rmdir()
            raise HTTPException(400, {"message": "no reviewable documents", "skipped": skipped})
        design_docs = [d for d in documents if classify(Path(d)) == "adr"]
        notes = []
        if mode == "design-set" and len(design_docs) < 2:
            mode = "per-document"
            notes.append("only one design document: checked on its own")
        (folder / "rules.yaml").write_text(to_yaml(combined), encoding="utf-8")  # snapshot of the rules used
        meta = {"id": analysis_id, "org": org_id, "project": project_id, "pack": combined["title"], "packs": used,
                "threshold": threshold, "bedrock": bool(use_bedrock and bedrock), "mode": mode, "notes": notes,
                "documents": documents, "skipped": skipped, "status": "queued", "error": None,
                "progress": {"done": 0, "total": len(documents), "current": None},
                "edited": [], "created_at": _now(), "finished_at": None}
        store.write(analysis_id, "rule_sources.json", sources)
        store.write(analysis_id, "removals.json", removals)
        store.write(analysis_id, "meta.json", meta)
        start(store, analysis_id)
        return _public(meta)

    @project_api.get("/analyses/{analysis_id}")
    def get_analysis(org_id: str, project_id: str, analysis_id: str) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        meta = store.read(analysis_id, "meta.json")
        return {**_public(meta), "report": store.read(analysis_id, "report.json"),
                "removals": store.read(analysis_id, "removals.json", []),
                "reviews": store.read(analysis_id, "reviews.json", {})}

    @project_api.get("/analyses/{analysis_id}/documents/{document:path}")
    def get_document(org_id: str, project_id: str, analysis_id: str, document: str) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        meta = store.read(analysis_id, "meta.json")
        if document not in meta["documents"]:
            raise NotFound("document not found")
        text = store.text_path(analysis_id, document).read_text(encoding="utf-8")
        doc = document_from_text(document, text)
        return {"path": document, "kind": doc.kind if doc else None, "text": text,
                "original_format": Path(document).suffix.lower().lstrip(".") or "text",
                "edited": document in meta.get("edited", []),
                "sections": [{"id": s.id, "heading": s.heading, "start_line": s.start_line} for s in (doc.sections if doc else [])]}

    @project_api.get("/analyses/{analysis_id}/export/expected.json")
    def export_expected(org_id: str, project_id: str, analysis_id: str) -> Response:
        store = analyses(org_id, project_id)
        meta = store.read(analysis_id, "meta.json")
        reviews = store.read(analysis_id, "reviews.json", {})
        expected = {"pack": meta["pack"], "note": f"Human review in the UI, analysis {analysis_id}.",
                    "expected": [{"rule": r["rule_id"], "file": r["document"], "verdict": r["verdict"],
                                  **({"note": r["note"]} if r.get("note") else {})}
                                 for r in sorted(reviews.values(), key=lambda r: (r["document"], r["rule_id"]))]}
        return Response(json.dumps(expected, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="expected-{analysis_id}.json"'})

    @project_api.get("/analyses/{analysis_id}/export/report.json")
    def export_report(org_id: str, project_id: str, analysis_id: str) -> Response:
        store = analyses(org_id, project_id)
        report = store.read(analysis_id, "report.json")
        if report is None:
            raise HTTPException(409, "the analysis has not finished")
        reviews = store.read(analysis_id, "reviews.json", {})
        for f in report["findings"]:
            review = reviews.get(f["id"])
            if review:
                f["human_decision"], f["human_verdict"] = review["decision"], review["verdict"]
                if review.get("fix"):
                    f["approved_fix"] = review["fix"]
        return Response(json.dumps(report, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="report-{analysis_id}.json"'})

    @project_api.get("/analyses/{analysis_id}/export/rules.yaml")
    def export_rules(org_id: str, project_id: str, analysis_id: str) -> PlainTextResponse:
        folder = analyses(org_id, project_id).folder(analysis_id)
        return PlainTextResponse((folder / "rules.yaml").read_text(encoding="utf-8"),
                                 headers={"Content-Disposition": f'attachment; filename="rules-{analysis_id}.yaml"'})

    @project_api.get("/analyses/{analysis_id}/export/document/{document:path}")
    def export_document(org_id: str, project_id: str, analysis_id: str, document: str) -> PlainTextResponse:
        store = analyses(org_id, project_id)
        meta = store.read(analysis_id, "meta.json")
        if document not in meta["documents"]:
            raise NotFound("document not found")
        text = store.text_path(analysis_id, document).read_text(encoding="utf-8")
        name = Path(document).name
        if classify(Path(document)) == "adr" and not name.lower().endswith(".md"):
            name = Path(name).stem + ".md"   # an edited PDF or Word file comes back as Markdown
        return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @project_api.put("/analyses/{analysis_id}/reviews/{finding_id:path}")
    def put_review(org_id: str, project_id: str, analysis_id: str, finding_id: str, body: ReviewIn) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        report = store.read(analysis_id, "report.json")
        finding = next((f for f in (report or {}).get("findings", []) if f["id"] == finding_id), None)
        if finding is None:
            raise NotFound("finding not found")
        tool_verdict = TOOL_VERDICT.get(finding["status"])  # needs_review has none
        if tool_verdict is None:  # needs_review: the tool made no call, the person makes it
            if body.decision != "resolved" or body.verdict is None:
                raise HTTPException(422, "a needs_review finding is resolved with a verdict: gap, compliant or not_applicable")
            verdict = body.verdict
        elif body.decision == "approved":
            verdict = tool_verdict
        elif body.decision == "rejected" and body.verdict not in (None, tool_verdict):
            verdict = body.verdict
        else:
            raise HTTPException(422, "a rejection needs a verdict that differs from the tool's")
        review = {"finding_id": finding_id, "rule_id": finding["rule_id"], "document": finding["document"],
                  "decision": body.decision, "verdict": verdict, "tool_status": finding["status"],
                  "note": body.note.strip(), "fix": (body.fix or "").strip() or None, "reviewed_at": _now()}
        with store.lock:
            reviews = store.read(analysis_id, "reviews.json", {})
            reviews[finding_id] = review
            store.write(analysis_id, "reviews.json", reviews)
        return review

    @project_api.delete("/analyses/{analysis_id}/reviews/{finding_id:path}", status_code=204)
    def delete_review(org_id: str, project_id: str, analysis_id: str, finding_id: str) -> Response:
        store = analyses(org_id, project_id)
        with store.lock:
            reviews = store.read(analysis_id, "reviews.json", {})
            reviews.pop(finding_id, None)
            store.write(analysis_id, "reviews.json", reviews)
        return Response(status_code=204)

    @project_api.put("/analyses/{analysis_id}/documents/{document:path}")
    def put_document(org_id: str, project_id: str, analysis_id: str, document: str, body: TextIn) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        with store.lock:
            meta = store.read(analysis_id, "meta.json")
            if document not in meta["documents"]:
                raise NotFound("document not found")
            cleaned, removed = clean(body.text, classify(Path(document)) or "adr")
            store.text_path(analysis_id, document).write_text(cleaned, encoding="utf-8")
            if removed:
                store.write(analysis_id, "removals.json", store.read(analysis_id, "removals.json", [])
                            + [{"document": document, "on_edit": True, **r.to_dict()} for r in removed])
            if document not in meta.get("edited", []):
                meta.setdefault("edited", []).append(document)
                store.write(analysis_id, "meta.json", meta)
        return get_document(org_id, project_id, analysis_id, document)

    @project_api.post("/analyses/{analysis_id}/documents/{document:path}/recheck", status_code=202)
    def recheck(org_id: str, project_id: str, analysis_id: str, document: str) -> dict[str, Any]:
        store = analyses(org_id, project_id)
        with store.lock:
            meta = store.read(analysis_id, "meta.json")
            if document not in meta["documents"]:
                raise NotFound("document not found")
            if meta["status"] in ("queued", "running"):
                raise HTTPException(409, "an analysis is already running")
            meta.update(status="queued", error=None)
            store.write(analysis_id, "meta.json", meta)
        start(store, analysis_id, only=document)
        return _public(meta)

    app.include_router(project_api)

    # ---- the built React app -----------------------------------------------------------------
    if ui_dist and Path(ui_dist, "index.html").exists():
        dist = Path(ui_dist)
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(dist / "index.html")

    return app


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _rule_summary(rule: dict) -> dict[str, Any]:
    return {"id": rule["id"], "title": rule["title"], "severity": rule["severity"],
            "applies_to": rule["applies_to"], "method": "decider" if "decider" in rule else "code",
            # how a Decider rule is aggregated (not to be confused with the source's organization/project scope)
            "applies_per": rule.get("decider", {}).get("scope", "section") if "decider" in rule else None}


def _pack_summary(data: dict) -> dict[str, Any]:
    return {"id": data.get("pack"), "title": data.get("title"), "version": str(data.get("version", "")),
            "description": " ".join(str(data.get("description", "")).split()),
            "rules": [_rule_summary(r) for r in data.get("rules", []) if isinstance(r, dict) and "id" in r],
            **({"error": data["error"]} if data.get("error") else {})}


def _public(meta: dict) -> dict[str, Any]:
    return {k: meta.get(k) for k in ("id", "org", "project", "pack", "packs", "threshold", "bedrock", "mode", "notes", "documents",
                                     "skipped", "status", "error", "progress", "edited", "created_at", "finished_at")}


def _merge(report: dict, partial: dict, document: str) -> dict:
    """Replace one document's findings after a re-check; keep the others."""
    findings = [f for f in report["findings"] if f["document"] != document] + partial["findings"]
    order = {path: i for i, path in enumerate(report["documents"])}
    findings.sort(key=lambda f: (order.get(f["document"], 0), f["rule_id"]))
    summary = {s: sum(f["status"] == s for f in findings) for s in ("gap", "needs_review", "covered", "not_applicable")}
    rechecks = report.get("rechecks", []) + [{"document": document, "at": _now(), "decider": partial.get("decider", {})}]
    return {**report, "findings": findings, "summary": summary, "rechecks": rechecks}
