"""Organisations, general and project rule packs, and isolation between projects."""
import time

import pytest
import yaml

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from conftest import ROOT, oracle  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shodhaka.decider import ScriptedDecider  # noqa: E402
from shodhaka.rules.pack import RulePackError, compose  # noqa: E402
from shodhaka.web.api import create_app  # noqa: E402

ADR = ROOT / "samples" / "acme-arch" / "visible" / "adr" / "adr-002-billing-invoices.md"
TEMPLATE = yaml.safe_load((ROOT / "rule-packs" / "acme-arch.yaml").read_text())


def pack(pack_id, *rules):
    return {"pack": pack_id, "version": "1", "title": pack_id, "rules": list(rules)}


def code_rule(rule_id, check="secret_scan", severity="high"):
    return {"id": rule_id, "title": f"rule {rule_id}", "severity": severity, "applies_to": ["config"],
            "requirement": "something", "deterministic": {"check": check}}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(tmp_path / "ws", ROOT / "rule-packs", lambda: ScriptedDecider(oracle), threshold=0.75))


def test_compose_project_overrides_general_and_rejects_clash_in_one_layer():
    combined, sources = compose([pack("general", code_rule("SEC-01"), code_rule("SEC-02"))],
                                [pack("local", code_rule("SEC-02", severity="low"))])
    assert [r["id"] for r in combined["rules"]] == ["SEC-01", "SEC-02"]
    assert combined["rules"][1]["severity"] == "low"
    assert sources["SEC-02"] == {"scope": "project", "pack": "local", "overrides": "general"}
    assert sources["SEC-01"]["scope"] == "organization"
    with pytest.raises(RulePackError, match="SEC-01"):
        compose([pack("a", code_rule("SEC-01")), pack("b", code_rule("SEC-01"))], [])


def test_register_org_projects_and_rules_in_effect(api):
    org = api.post("/api/orgs", json={"name": "Acme", "description": "shop"}).json()["id"]
    assert api.post("/api/orgs", json={"name": "acme"}).status_code == 409          # names are unique
    assert api.post(f"/api/orgs/{org}/packs", json={"template": "acme-architecture"}).status_code == 201
    shop = api.post(f"/api/orgs/{org}/projects", json={"name": "Shop"}).json()["id"]
    pay = api.post(f"/api/orgs/{org}/projects", json={"name": "Payments"}).json()["id"]

    # Payments tightens ARCH-07 to high severity and adds its own rule
    override = dict(next(r for r in TEMPLATE["rules"] if r["id"] == "ARCH-07"), severity="high")
    body = {"pack": pack("payments-rules", override, code_rule("PAY-01"))}
    assert api.post(f"/api/orgs/{org}/projects/{pay}/packs", json=body).status_code == 201

    shop_rules = {r["id"]: r for r in api.get(f"/api/orgs/{org}/projects/{shop}").json()["rules"]}
    pay_rules = {r["id"]: r for r in api.get(f"/api/orgs/{org}/projects/{pay}").json()["rules"]}
    assert "PAY-01" not in shop_rules and shop_rules["ARCH-07"]["severity"] == "low"
    assert pay_rules["PAY-01"]["scope"] == "project"
    assert pay_rules["PAY-01"]["applies_per"] is None and shop_rules["ARCH-04"]["applies_per"] == "document"
    assert pay_rules["ARCH-07"]["severity"] == "high"
    assert pay_rules["ARCH-07"]["overrides"] == "acme-architecture"

    # a project can switch a general pack off
    r = api.patch(f"/api/orgs/{org}/projects/{shop}", json={"excluded_general_packs": ["acme-architecture"]})
    assert r.json()["rules"] == [] and "no rules" in r.json()["rules_problem"]
    assert api.post(f"/api/orgs/{org}/projects/{shop}/analyses", files=[("files", (ADR.name, ADR.read_bytes()))]).status_code == 422


def test_projects_and_orgs_are_isolated(api):
    a = api.post("/api/orgs", json={"name": "A"}).json()["id"]
    b = api.post("/api/orgs", json={"name": "B"}).json()["id"]
    api.post(f"/api/orgs/{a}/packs", json={"template": "acme-architecture"})
    pa = api.post(f"/api/orgs/{a}/projects", json={"name": "P"}).json()["id"]
    pa2 = api.post(f"/api/orgs/{a}/projects", json={"name": "Q"}).json()["id"]
    pb = api.post(f"/api/orgs/{b}/projects", json={"name": "P"}).json()["id"]   # same name, other org: fine

    r = api.post(f"/api/orgs/{a}/projects/{pa}/analyses", files=[("files", (ADR.name, ADR.read_bytes()))])
    analysis = r.json()["id"]
    assert api.get(f"/api/orgs/{a}/projects/{pa}/analyses/{analysis}").status_code == 200
    assert api.get(f"/api/orgs/{a}/projects/{pa2}/analyses/{analysis}").status_code == 404   # other project
    assert api.get(f"/api/orgs/{b}/projects/{pb}/analyses/{analysis}").status_code == 404    # other org
    assert api.get(f"/api/orgs/{b}/projects/{pa}").status_code == 404                        # project of org A via org B
    assert api.get(f"/api/orgs/{a}/projects/{pa2}/analyses").json() == []
    assert api.get(f"/api/orgs/{b}").json()["general_packs"] == []                          # B never saw A's packs


def test_pack_editing_validation_and_snapshot(api):
    org = api.post("/api/orgs", json={"name": "Acme"}).json()["id"]
    bad = api.post(f"/api/orgs/{org}/packs", json={"yaml": "pack: x\nrules: []\n"})
    assert bad.status_code == 422 and bad.json()["detail"]["problems"]
    text = "# our security baseline\n" + yaml.safe_dump(pack("baseline", code_rule("SEC-01")))
    assert api.post(f"/api/orgs/{org}/packs", json={"yaml": text}).status_code == 201
    assert api.get(f"/api/orgs/{org}/packs/baseline").json()["yaml"].startswith("# our security baseline")  # comments kept
    clash = api.post(f"/api/orgs/{org}/packs", json={"pack": pack("other", code_rule("SEC-01"))})
    assert clash.status_code == 409 and "SEC-01" in clash.json()["detail"]
    renamed = api.put(f"/api/orgs/{org}/packs/baseline", json={"pack": pack("renamed", code_rule("SEC-01"))})
    assert renamed.status_code == 409

    project = api.post(f"/api/orgs/{org}/projects", json={"name": "P"}).json()["id"]
    cfg = ("app.yml", b"spring:\n  application:\n    name: x\n  datasource:\n    password: hunter2\n")
    analysis = api.post(f"/api/orgs/{org}/projects/{project}/analyses", files=[("files", cfg)]).json()["id"]
    for _ in range(200):
        body = api.get(f"/api/orgs/{org}/projects/{project}/analyses/{analysis}").json()
        if body["status"] == "done":
            break
        time.sleep(0.02)
    finding = body["report"]["findings"][0]
    assert finding["status"] == "gap" and finding["rule_source"]["pack"] == "baseline"
    # editing the pack later does not change what this analysis ran with
    api.put(f"/api/orgs/{org}/packs/baseline", json={"pack": pack("baseline", code_rule("SEC-01", "health_endpoint"))})
    rules = api.get(f"/api/orgs/{org}/projects/{project}/analyses/{analysis}/export/rules.yaml").text
    assert "secret_scan" in rules and "health_endpoint" not in rules


def test_validate_endpoint_round_trips_form_and_yaml(api):
    out = api.post("/api/packs/validate", json={"pack": pack("p1", code_rule("SEC-01"))}).json()
    assert out["valid"] and "SEC-01" in out["yaml"]
    back = api.post("/api/packs/validate", json={"yaml": out["yaml"]}).json()
    assert back["pack"]["rules"][0]["id"] == "SEC-01"
    assert not api.post("/api/packs/validate", json={"yaml": "a: [unclosed"}).json()["valid"]


def pack_oracle(state, key, question):
    """Stands in for Decider on the recommendation question: picks the pack whose words match the text."""
    if key != "packs":
        return oracle(state, key, question)
    text = state.lower()
    for option, description in question["criteria"].items():
        d = description.lower()
        if ("dora" in d and "incident" in text and "continuity" in text) or ("27001" in d and "access control" in text):
            return option, 0.9
    return "none", 0.6


def test_recommend_packs_then_analyse_with_the_chosen_ones(tmp_path):
    from shodhaka.decider import Answer

    class Scripted(ScriptedDecider):
        def ask(self, state, questions):
            answers = super().ask(state, questions)
            if "packs" in questions:  # give the choice answer realistic probabilities
                pick = answers["packs"].option
                probs = {k: (0.9 if k == pick else 0.1 / len(questions["packs"]["criteria"])) for k in questions["packs"]["criteria"]}
                answers["packs"] = Answer(pick, 0.9, probs)
            return answers

    api = TestClient(create_app(tmp_path / "ws", ROOT / "rule-packs", lambda: Scripted(pack_oracle), threshold=0.75))
    org = api.post("/api/orgs", json={"name": "Acme Bank"}).json()["id"]
    api.post(f"/api/orgs/{org}/packs", json={"template": "acme-architecture"})
    project = api.post(f"/api/orgs/{org}/projects", json={"name": "Compliance"}).json()["id"]
    base = f"/api/orgs/{org}/projects/{project}"

    refs = {c["ref"]: c for c in api.get(f"{base}/candidates").json()}
    assert refs["org:acme-architecture"]["in_effect"] and refs["template:dora"]["source"] == "template"
    assert "template:iso27001" in refs and "template:acme-architecture" not in refs    # already added to the org

    policies = ROOT / "samples" / "policies"
    files = [("files", (p.name, p.read_bytes())) for p in sorted(policies.glob("*.md")) if p.name != "dora-ict-risk-management-framework.md"]
    rec = api.post(f"{base}/recommend", files=files).json()
    picks = {d["document"]: d["pick"] for d in rec["documents"]}
    assert picks == {"access-control-policy.md": "template:iso27001", "ict-incident-and-continuity-policy.md": "template:dora"}
    assert set(rec["recommended"]) == {"template:dora", "template:iso27001"}
    assert api.get(f"{base}/analyses").json() == []                                    # recommending stored nothing

    r = api.post(f"{base}/analyses", files=files, data={"packs": "template:dora,template:iso27001"})
    assert r.status_code == 201 and r.json()["packs"] == ["dora", "iso27001"]
    for _ in range(300):
        body = api.get(f"{base}/analyses/{r.json()['id']}").json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert body["status"] == "done", body["error"]
    rule_ids = {f["rule_id"] for f in body["report"]["findings"]}
    assert any(x.startswith("DORA-") for x in rule_ids) and any(x.startswith("ISO-") for x in rule_ids)
    assert not any(x.startswith("ARCH-") for x in rule_ids)                           # not ticked, not checked
    assert body["report"]["findings"][0]["rule_source"]["scope"] == "template"
    assert api.post(f"{base}/analyses", files=files, data={"packs": "template:nope"}).status_code == 409


def test_shipped_packs_are_valid():
    from shodhaka.rules.pack import load_pack
    for path in (ROOT / "rule-packs").glob("*.yaml"):
        assert load_pack(path).rules
