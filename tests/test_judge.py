import json

from conftest import ROOT

from shodhaka.evaluation.judge import CRITERIA, Judge, judge_report, table, write
from shodhaka.rules.pack import load_pack

PACK = load_pack(ROOT / "rule-packs" / "acme-arch.yaml")


class FakeClient:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def converse(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"][0]["text"])
        return {"output": {"message": {"content": [{"text": self.replies.pop(0)}]}},
                "usage": {"inputTokens": 100, "outputTokens": 20}}


def reply(score):
    return "Here you go: " + json.dumps({"scores": {key: score for key, _, _ in CRITERIA}, "rationale": "ok"})


def report(fix_source="bedrock"):
    return {"findings": [
        {"rule_id": "ARCH-01", "document": "adr.md", "status": "gap", "decided_by": "decider",
         "reason": "gap in section 'Data'", "suggested_fix": "Call the API on orders.internal instead.",
         "fix_source": fix_source, "evidence": [{"text": "Loyalty reads the orders table on db1.corp."}]},
        {"rule_id": "ARCH-02", "document": "adr.md", "status": "covered", "decided_by": "decider", "evidence": []},
    ]}


def test_only_gaps_are_judged_and_identifiers_are_redacted():
    client = FakeClient([reply(4)])
    result = judge_report(report(), PACK, Judge("judge-model", "eu-central-1", client))
    assert result["graded"] == 1 and result["means"]["resolves_gap"] == 4 and result["overall"] == 4
    assert result["system"] == "Fixes drafted by Nova Lite"
    sent = client.prompts[0]
    assert "db1.corp" not in sent and "orders.internal" not in sent and "[HOST_" in sent


def test_unparsable_replies_are_retried_then_counted():
    judge = Judge("judge-model", "eu-central-1", FakeClient(["no json", "still none"]))
    result = judge_report(report(), PACK, judge)
    assert result["graded"] == 0 and judge.failures == 1 and judge.calls == 2


def test_write_produces_table_json_and_chart(tmp_path):
    results = [judge_report(report(), PACK, Judge("m", "r", FakeClient([reply(5)]))),
               judge_report(report("rule-hint"), PACK, Judge("m", "r", FakeClient([reply(3)])))]
    write(tmp_path, results, {"judge_model": "m"})
    assert (tmp_path / "judge.svg").read_text().count("<path") == 12
    assert "| **Overall** | **5.00** | **3.00** |" in table(results)
    assert json.loads((tmp_path / "judge.json").read_text())["results"][1]["system"] == "Rule-owner fix hints (offline)"
