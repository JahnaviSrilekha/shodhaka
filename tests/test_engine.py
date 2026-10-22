from pathlib import Path

from gapanalyzer.decider import ScriptedDecider
from gapanalyzer.engine import analyze
from gapanalyzer.evaluate import evaluate
from gapanalyzer.report import write_html, write_json
from gapanalyzer.suggest import add_fixes
from conftest import VISIBLE


def by_key(report):
    return {(f["rule_id"], f["document"]): f for f in report["findings"]}


RULES = {"ARCH-01", "ARCH-02", "ARCH-04", "ARCH-05"}


def _content_sections(docs):
    return sum(len([s for s in d.sections if s.heading != "Preamble"]) for d in docs if d.kind == "adr")


def test_two_stage_asks_all_rules_per_section_then_only_on_topic_ones(pack, visible_docs, scripted):
    analyze(pack, visible_docs, scripted)
    requests = [q for _, q in scripted.requests if "evidence" not in q]
    stage1 = [q for q in requests if set(q) == RULES and all(v["instructions"].startswith("Does this section talk about") for v in q.values())]
    stage2 = [q for q in requests if q not in stage1]
    assert len(stage1) == _content_sections(visible_docs)          # one relevance request per section, metadata skipped
    assert stage2 and all(set(q) < RULES or set(q) == RULES for q in stage2)
    assert all(all("meet this requirement" in v["instructions"] for v in q.values()) for q in stage2)


def test_choice_strategy_one_request_per_section(pack, visible_docs, scripted):
    analyze(pack, visible_docs, scripted, strategy="choice")
    requests = [q for _, q in scripted.requests if "evidence" not in q]
    assert len(requests) == _content_sections(visible_docs) and all(set(q) == RULES for q in requests)


def test_off_topic_section_cannot_drag_a_covered_rule_into_review(pack, visible_docs):
    """The real-run failure: ARCH-04 covered at 0.95 in 'Tracing', but a weak 0.43 gap vote from the
    unrelated 'Calls to Payment' section escalated it. With two stages, off-topic sections do not vote."""
    def script(state, key, q):
        if q["instructions"].startswith("Does this section talk about"):
            return ("true", 0.9) if "Section: Tracing" in state else ("false", 0.8)
        return ("true", 0.95)
    doc = next(d for d in visible_docs if d.path.endswith("adr-001-order-saga.md"))
    f = by_key(analyze(pack, [doc], ScriptedDecider(script)))[("ARCH-04", doc.path)]
    assert f["status"] == "covered"


def test_calibrate_rescores_without_model_calls(pack, visible_docs, scripted):
    from gapanalyzer.evaluate import calibrate
    report = analyze(pack, visible_docs, scripted)
    calls = scripted.stats.calls
    rows = calibrate(report, VISIBLE / "expected.json")
    assert scripted.stats.calls == calls and [r["threshold"] for r in rows][0] == 0.5
    assert all(r["false_alarm_rate"] == 0.0 for r in rows)


def test_pipeline_matches_ground_truth_with_oracle(pack, visible_docs, scripted):
    report = analyze(pack, visible_docs, scripted)
    result = evaluate(report, VISIBLE / "expected.json")
    assert result["missing_findings"] == []
    assert result["exact_accuracy"] == 1.0
    assert result["false_alarm_rate"] == 0.0


def test_prompt_injection_does_not_turn_a_gap_into_a_pass(pack, visible_docs, scripted):
    f = by_key(analyze(pack, visible_docs, scripted))[("ARCH-01", "adr/adr-005-loyalty-points.md")]
    assert f["status"] == "gap"


def test_low_confidence_escalates_never_passes(pack, visible_docs):
    unsure = ScriptedDecider(lambda s, k, q: ("false", 0.6) if q["type"] == "noul"
                             else (next(iter(q["criteria"])), 0.55))
    report = analyze(pack, visible_docs, unsure)
    decider_findings = [f for f in report["findings"] if f["decided_by"] == "decider"]
    assert decider_findings and all(f["status"] in ("needs_review", "not_applicable") for f in decider_findings)
    assert not any(f["status"] == "covered" for f in decider_findings)


def test_gap_has_sentence_level_evidence(pack, visible_docs, scripted):
    f = by_key(analyze(pack, visible_docs, scripted))[("ARCH-01", "adr/adr-002-billing-invoices.md")]
    assert f["evidence"][0]["section"] == "Reading order data"
    assert "Order service's PostgreSQL" in f["evidence"][0]["text"]


def test_offline_fixes_and_report_files(pack, visible_docs, scripted, tmp_path: Path):
    report = add_fixes(analyze(pack, visible_docs, scripted), pack, writer=None)
    gaps = [f for f in report["findings"] if f["status"] == "gap"]
    assert gaps and all(f["suggested_fix"] and f["fix_source"] == "rule-hint" for f in gaps)
    assert report["egress"]["bytes_sent"] == 0
    write_json(report, tmp_path / "report.json")
    write_html(report, tmp_path / "report.html")
    page = (tmp_path / "report.html").read_text()
    assert "data-testid='finding-ARCH-01:adr/adr-002-billing-invoices.md'" in page
    assert "S3cretBilling" not in page and "tk_live" not in page


def _s(heading, verdict, conf):
    return {"section": heading, "heading": heading, "option": verdict, "verdict": verdict, "confidence": conf}


def test_gate_document_scope_lets_one_clear_section_cover_the_document():
    from gapanalyzer.engine import gate
    sections = [_s("Publishing invoices", "gap", 0.896), _s("Tax calculation", "compliant", 0.868)]
    assert gate(sections, 0.8, "section")[0] == "gap"
    status, _, reason = gate(sections, 0.8, "document")
    assert status == "covered" and "does not mention it" in reason


def test_gate_document_scope_still_reports_gap_when_nothing_complies():
    from gapanalyzer.engine import gate
    assert gate([_s("Messages", "gap", 0.966)], 0.8, "document")[0] == "gap"


def test_stage_one_uses_the_rules_short_topic(pack):
    from gapanalyzer.compiler import relevance_question
    q = relevance_question(pack.rule("ARCH-05"))
    assert q["instructions"].startswith("Does this section talk about a request/response call")


def test_design_set_presence_rule_met_anywhere_prohibition_broken_anywhere(pack, visible_docs, scripted):
    from gapanalyzer.engine import DESIGN_SET
    report = analyze(pack, visible_docs, scripted, mode="design-set")
    adrs = sorted(d.path for d in visible_docs if d.kind == "adr")
    assert report["mode"] == "design-set" and report["design_set"] == adrs
    by_rule = {f["rule_id"]: f for f in report["findings"] if f["document"] == DESIGN_SET}
    assert set(by_rule) == {"ARCH-01", "ARCH-02", "ARCH-04", "ARCH-05"}       # one finding per Decider rule

    # ARCH-04 (scope document): ADR-003 says no correlation ids, ADR-002 carries X-Correlation-Id -> met
    assert by_rule["ARCH-04"]["status"] == "covered"
    meets = [e for e in by_rule["ARCH-04"]["evidence"] if e["role"] == "meets"]
    assert meets and "x-correlation-id" in meets[0]["text"].lower()

    # ARCH-01 (scope section): ADR-002 reads another service's database -> gap for the whole design,
    # with the breaking quote first and a section that meets the rule shown next to it
    f = by_rule["ARCH-01"]
    assert f["status"] == "gap" and f["evidence"][0]["role"] == "breaks"
    assert f["evidence"][0]["document"].endswith("adr-002-billing-invoices.md")
    assert any(e["role"] == "meets" for e in f["evidence"]) and f["documents"] == adrs
    assert all("#" in s["section"] and " › " in s["heading"] for s in f["sections"])

    # config files and Dockerfiles stay file by file
    code = [x for x in report["findings"] if x["decided_by"] == "code"]
    assert code and all(x["document"] != DESIGN_SET for x in code)


def test_per_document_mode_is_unchanged(pack, visible_docs, scripted):
    from gapanalyzer.engine import DESIGN_SET
    report = analyze(pack, visible_docs, scripted)
    assert report["mode"] == "per-document" and not any(f["document"] == DESIGN_SET for f in report["findings"])
