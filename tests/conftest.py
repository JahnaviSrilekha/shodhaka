from pathlib import Path

import pytest

from gapanalyzer.decider import ScriptedDecider
from gapanalyzer.documents import discover
from gapanalyzer.rulepack import load_pack

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "rule-packs" / "acme-arch.yaml"
VISIBLE = ROOT / "samples" / "acme-arch" / "visible"


@pytest.fixture
def pack():
    return load_pack(PACK)


@pytest.fixture
def visible_docs():
    return discover(VISIBLE)


# Keyword oracle standing in for the model in tests. It is NOT a baseline for the article:
# it only lets the pipeline (compiler, gating, aggregation, evidence, report) be tested offline.
SIGNALS = {
    "ARCH-01": [("accesses-other-service-data", ("connects directly to the order service", "read replica of the payment",
                                                 "directly in the customer service")),
                ("owns-own-data", ("owns the", "does not read any other", "never read these tables"))],
    "ARCH-02": [("not-guaranteed", ("after the invoice rows are committed",)),
                ("guaranteed", ("outbox",))],
    "ARCH-04": [("no-correlation-id", ("not to add correlation",)),
                ("carries-correlation-id", ("x-correlation-id",))],
    "ARCH-05": [("missing-timeout-or-fallback", ("calls the external tax service over http", "through an external provider")),
                ("timeout-and-fallback", ("timeout is", "second timeout"))],
}


def oracle(state: str, key: str, question: dict):
    text = " ".join(state.lower().split())  # PDFs wrap lines mid-sentence
    if key == "evidence":
        # pick the sentence sharing the most words with the claim
        claim = set(question["instructions"].lower().split())
        best = max(question["criteria"], key=lambda k: len(claim & set(question["criteria"][k].lower().split())))
        return best, 0.8
    matched = next((option for option, needles in SIGNALS.get(key, []) if any(n in text for n in needles)), None)
    if question["type"] == "noul":
        if question["instructions"].startswith(("Does this section discuss the topic", "Does this section talk about")):
            return ("true", 0.95) if matched else ("false", 0.95)       # stage 1: on topic?
        if question["instructions"].startswith("Does what this section describes meet"):
            compliant = {"owns-own-data", "guaranteed", "carries-correlation-id", "timeout-and-fallback"}
            return ("true", 0.95) if matched in compliant else ("false", 0.95)  # stage 2: compliant?
        return "false", 0.95
    for option, needles in SIGNALS.get(key, []):
        if any(n in text for n in needles):
            return option, 0.96
    return "not-discussed", 0.97


@pytest.fixture
def scripted():
    return ScriptedDecider(oracle)
