"""No Decider needed: `ask` is a fake that answers from keywords."""

import json
from pathlib import Path

from coverage_check import COVERED, GAP, NEEDS_REVIEW, NOT_APPLICABLE, Answer, Rule, check, gate

EXAMPLE = json.loads(Path(__file__).with_name("example.json").read_text())
RULES = [Rule(**r) for r in EXAMPLE["rules"]]

ON_TOPIC = {"ARCH-01": "schema", "ARCH-03": "calls", "ARCH-04": "correlation"}
BREAKS = {"ARCH-01": "orders table"}


def fake_ask(state, questions):
    text = state.lower()
    stage_one = next(iter(questions.values()))["instructions"].startswith("Does this section talk")
    if stage_one:
        return {rule: 0.9 if ON_TOPIC[rule] in text else 0.1 for rule in questions}
    return {rule: 0.05 if BREAKS.get(rule, "\0") in text else 0.95 for rule in questions}


def test_example_matches_expected():
    verdicts = {v.rule: v.status for v in check(EXAMPLE["sections"], RULES, fake_ask)}
    assert verdicts == EXAMPLE["expected"]


def test_unsure_answers_go_to_a_person():
    assert gate([Answer("Data", "gap", 0.6)], 0.75)[0] == NEEDS_REVIEW
    assert gate([Answer("Data", "compliant", 0.6)], 0.75)[0] == NEEDS_REVIEW


def test_one_confident_gap_wins_for_section_scope():
    answers = [Answer("A", "compliant", 0.99), Answer("B", "gap", 0.8)]
    assert gate(answers, 0.75, "section")[0] == GAP


def test_one_section_is_enough_for_document_scope():
    answers = [Answer("A", "compliant", 0.9), Answer("B", "gap", 0.8)]
    assert gate(answers, 0.75, "document")[0] == COVERED


def test_nothing_on_topic_is_not_applicable():
    assert gate([], 0.75)[0] == NOT_APPLICABLE
