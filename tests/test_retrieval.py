import pytest

from gapanalyzer.engine import analyze
from gapanalyzer.evaluate import compare, evaluate
from gapanalyzer.retrieval import BM25, rule_query, shortlist
from conftest import VISIBLE

# where each planted gap or compliance statement actually lives (rule, file, section heading)
EVIDENCE = [
    ("ARCH-01", "adr-002-billing-invoices.md", "Reading order data"),
    ("ARCH-02", "adr-002-billing-invoices.md", "Publishing invoices"),
    ("ARCH-05", "adr-002-billing-invoices.md", "Tax calculation"),
    ("ARCH-01", "adr-001-order-saga.md", "Data ownership"),
    ("ARCH-02", "adr-001-order-saga.md", "Event publishing"),
    ("ARCH-04", "adr-001-order-saga.md", "Tracing"),
    ("ARCH-05", "adr-001-order-saga.md", "Calls to Payment"),
    ("ARCH-04", "adr-003-notification-service.md", "Messages"),
    ("ARCH-01", "adr-005-loyalty-points.md", "Data"),
]


def test_bm25_ranks_the_relevant_section_in_the_top_3(pack, visible_docs):
    docs = {d.path.split("/")[-1]: d for d in visible_docs}
    for rule_id, name, heading in EVIDENCE:
        sections = [s for s in docs[name].sections if s.heading != "Preamble"]
        picks = shortlist(BM25(), [pack.rule(rule_id)], [f"{s.heading}. {s.text}" for s in sections], 3)
        assert heading in {sections[i].heading for i in picks[rule_id]}, (rule_id, name)


def test_rule_query_uses_topic_and_descriptions(pack):
    q = rule_query(pack.rule("ARCH-05"))
    assert "request/response call" in q and "timeout" in q


def test_retrieval_cuts_calls_and_keeps_results(pack, visible_docs, scripted):
    from gapanalyzer.decider import ScriptedDecider
    from conftest import oracle
    full = analyze(pack, visible_docs, scripted)
    short_decider = ScriptedDecider(oracle)
    short = analyze(pack, visible_docs, short_decider, ranker=BM25(), top_k=2)
    assert short["retrieval"]["pairs_checked"] < short["retrieval"]["pairs_total"]
    assert short_decider.stats.questions < scripted.stats.questions
    assert evaluate(short, VISIBLE / "expected.json")["exact_accuracy"] == 1.0
    c = compare(full, short)
    assert c["retrieval_recall"] == 1.0 and c["findings_changed"] == []


def test_skipped_pairs_are_never_counted_as_compliant(pack, visible_docs, scripted):
    class Worst:
        name = "worst"
        def scores(self, query, docs):  # always picks the first section, whatever it is
            return [1.0] + [0.0] * (len(docs) - 1)
    report = analyze(pack, visible_docs, scripted, ranker=Worst(), top_k=1)
    skipped = [s for f in report["findings"] for s in f.get("sections", []) if s["option"] == "not-checked-retrieval"]
    assert skipped and all(s["verdict"] == "not_applicable" for s in skipped)
    assert not any(f["status"] == "covered" and all(s["option"] == "not-checked-retrieval" for s in f["sections"])
                   for f in report["findings"] if f["decided_by"] == "decider")


def test_retrieval_requires_two_stage(pack, visible_docs, scripted):
    with pytest.raises(ValueError):
        analyze(pack, visible_docs, scripted, strategy="choice", ranker=BM25())
