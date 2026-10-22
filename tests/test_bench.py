import json

from conftest import VISIBLE
from gapanalyzer.bench import BedrockDecider, _answer, cost, render, summarise, table
from gapanalyzer.engine import analyze
from gapanalyzer.evaluate import evaluate


class FakeBedrock:
    """Answers Converse calls like an LLM would: JSON with answer + confidence, sometimes with prose around it."""

    def __init__(self, oracle):
        self.oracle, self.calls = oracle, 0

    def converse(self, modelId, system, messages, inferenceConfig):
        self.calls += 1
        prompt = messages[0]["content"][0]["text"]
        state, _, qtext = prompt.partition("\nQuestions:\n")
        out = {}
        for key, question in self.questions.items():
            option, conf = self.oracle(state, key, question)
            out[key] = {"answer": option == "true" if question["type"] == "noul" else option, "confidence": conf}
        text = ("Sure! " if self.calls % 3 == 0 else "") + json.dumps(out)
        return {"output": {"message": {"content": [{"text": text}]}},
                "usage": {"inputTokens": len(prompt) // 4, "outputTokens": 30}, "metrics": {"latencyMs": 400}}


class Llm(BedrockDecider):
    def ask(self, state, questions):
        self.client.questions = questions  # let the fake see the typed questions
        return super().ask(state, questions)


def test_llm_answers_the_same_questions_and_is_scored_the_same_way(pack, visible_docs, scripted):
    from conftest import oracle
    llm = Llm("eu.amazon.nova-lite-v1:0", "eu-central-1", client=FakeBedrock(oracle))
    llm_report = analyze(pack, visible_docs, llm, threshold=0.75)
    dec_report = analyze(pack, visible_docs, scripted, threshold=0.75)
    llm_report["decider"] = llm.stats.as_dict()
    # same oracle behind both: identical findings prove the harness itself adds no difference
    assert [(f["id"], f["status"]) for f in llm_report["findings"]] == [(f["id"], f["status"]) for f in dec_report["findings"]]
    assert llm.stats.calls == scripted.stats.calls and llm.stats.failures == 0
    usd = cost(llm_report["decider"], 0.00006, 0.00024)
    row = summarise("llm", llm_report, evaluate(llm_report, VISIBLE / "expected.json"), 1.0, usd)
    assert row["usd_total"] > 0 and row["usd_per_1k_requests"] > 0 and row["latency_ms_p50"] == 400
    assert "| Exact accuracy |" in table([row])


def test_unparseable_and_odd_answers_become_unsure():
    noul = {"type": "noul", "instructions": "x"}
    choice = {"type": "choice", "instructions": "x", "criteria": {"a": "A", "b": "B"}}
    assert _answer(noul, {"answer": "yes", "confidence": 0.9}).p_true == 0.9
    assert _answer(noul, {"answer": False, "confidence": 0.2}).confidence == 0.5   # never below a coin flip
    assert _answer(choice, {"answer": "zzz", "confidence": 0.99}).confidence == 0.5  # unknown option
    assert "(choice, answer with one option key)" in render("S", {"q": choice})

    class Broken:
        def converse(self, **kw):
            return {"output": {"message": {"content": [{"text": "I think yes"}]}}, "usage": {}}
    llm = BedrockDecider("m", "r", client=Broken())
    answers = llm.ask("state", {"q": noul})
    assert answers["q"].confidence == 0.5 and llm.stats.failures == 1 and llm.stats.calls == 2  # retried once


def test_cli_refuses_to_send_text_without_consent(capsys):
    from gapanalyzer.cli import main
    assert main(["bench", "--pack", "rule-packs/acme-arch.yaml", "--docs", str(VISIBLE), "--expected", str(VISIBLE / "expected.json")]) == 1
    assert "WITHOUT redaction" in capsys.readouterr().err


def test_cli_reuses_a_decider_report_without_new_calls(pack, visible_docs, scripted, tmp_path):
    from gapanalyzer.cli import main
    report = analyze(pack, visible_docs, scripted, threshold=0.9)
    report["decider"] = scripted.stats.as_dict()
    (tmp_path / "r.json").write_text(json.dumps(report))
    code = main(["bench", "--pack", "rule-packs/acme-arch.yaml", "--docs", str(VISIBLE), "--expected", str(VISIBLE / "expected.json"),
                 "--decider-report", str(tmp_path / "r.json"), "--skip-llm", "--threshold", "0.75", "--out", str(tmp_path / "b")])
    assert code == 0
    saved = json.loads((tmp_path / "b" / "bench.json").read_text())
    assert saved["threshold"] == 0.75 and saved["results"][0]["exact_accuracy"] is not None
    assert (tmp_path / "b" / "bench.md").read_text().startswith("# Decider vs")
