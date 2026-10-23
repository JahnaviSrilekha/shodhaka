from types import SimpleNamespace

import pytest

from shodhaka.analysis.fixes import EgressLog, _interventions
from shodhaka.decider import ScriptedDecider
from shodhaka.documents.redact import Redactor


def test_redact_and_restore_round_trip():
    r = Redactor(extra_terms={"Stripe": "VENDOR"})
    text = "Billing reads jdbc:postgresql://10.20.30.40:5432/billing on order-db.acme.internal, key tk_live_9f8e7d6c5b4a, mail ops@acme.com, via Stripe."
    red = r.redact(text)
    for secret in ("10.20.30.40", "order-db.acme.internal", "tk_live_9f8e7d6c5b4a", "ops@acme.com", "Stripe"):
        assert secret not in red
    assert r.leaks(red) == []
    assert r.restore(red) == text


def _event(text):
    return SimpleNamespace(agent=SimpleNamespace(messages=[{"role": "user", "content": [{"text": text}]}]))


try:
    import strands  # noqa: F401
    HAS_STRANDS = True
except ImportError:
    HAS_STRANDS = False

needs_strands = pytest.mark.skipif(not HAS_STRANDS, reason='strands-agents not installed (pip install -e ".[bedrock]")')


@needs_strands
def test_egress_guard_blocks_unredacted_text_and_logs_bytes():
    EgressGuard, _ = _interventions()
    r = Redactor()
    safe = r.redact("The job connects to order-db.acme.internal directly.")
    log = EgressLog()
    guard = EgressGuard(r, ScriptedDecider(lambda s, k, q: ("false", 0.95)), log, "F1")
    assert guard.before_model_call(_event(safe)).type == "proceed"
    assert guard.before_model_call(_event("leak: order-db.acme.internal")).type == "deny"
    assert log.calls == 1 and log.blocked == 1 and log.bytes_sent == len(safe.encode())


@needs_strands
def test_egress_guard_uses_decider_for_names_regex_cannot_see():
    EgressGuard, _ = _interventions()
    guard = EgressGuard(Redactor(), ScriptedDecider(lambda s, k, q: ("true", 0.9)), EgressLog(), "F1")
    assert guard.before_model_call(_event("Ask Maria Schmidt in billing")).type == "deny"


@needs_strands
def test_fix_guard_guides_then_gives_up_after_two_tries(pack):
    _, FixGuard = _interventions()
    guard = FixGuard(ScriptedDecider(lambda s, k, q: ("false", 0.9)), pack.rule("ARCH-01"), "reads orders table")
    event = SimpleNamespace(tool_use={"name": "submit_fix", "input": {"fix": "be careful"}})
    assert [guard.before_tool_call(event).type for _ in range(3)] == ["guide", "guide", "proceed"]


def test_bedrock_guardrail_is_passed_on_and_an_intervention_falls_back_to_the_hint(monkeypatch):
    import strands
    import strands.models
    from conftest import ROOT

    from shodhaka.analysis.fixes import FixWriter, add_fixes
    from shodhaka.rules.pack import load_pack

    seen = {}

    class FakeModel:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    class FakeResult:
        stop_reason = "guardrail_intervened"

        def __str__(self):
            return "[blocked by the Bedrock guardrail]"

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def __call__(self, prompt):
            return FakeResult()

    monkeypatch.setattr(strands.models, "BedrockModel", FakeModel)
    monkeypatch.setattr(strands, "Agent", FakeAgent)
    pack = load_pack(ROOT / "rule-packs" / "acme-arch.yaml")
    report = {"findings": [{"id": "F1", "rule_id": "ARCH-01", "status": "gap", "reason": "r",
                            "evidence": [{"text": "reads the orders table"}]}]}
    writer = FixWriter(ScriptedDecider(lambda s, k, q: ("false", 0.9)), guardrail_id="gr-123", guardrail_version="1")
    add_fixes(report, pack, writer)
    assert seen["guardrail_id"] == "gr-123" and seen["guardrail_version"] == "1" and seen["guardrail_trace"] == "enabled"
    finding = report["findings"][0]
    assert finding["fix_source"] == "rule-hint (blocked by Bedrock guardrail)"
    assert finding["suggested_fix"] == pack.rule("ARCH-01").fix_hint
    assert report["egress"]["guardrail_interventions"] == 1 and report["egress"]["guardrail"] == "gr-123"
