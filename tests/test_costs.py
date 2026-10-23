from shodhaka.analysis.costs import add_run, run_usage, text_units


def test_bedrock_and_guardrail_costs_add_up_over_runs(monkeypatch):
    monkeypatch.setenv("SHODHAKA_GUARDRAIL_PRICE", "0.40")
    monkeypatch.delenv("SHODHAKA_PRICE_IN", raising=False)
    egress = {"bedrock_calls": 4, "blocked": 1, "input_tokens": 1_000_000, "output_tokens": 500_000,
              "guardrail": "gr-1", "guardrail_text_units": 10, "guardrail_interventions": 1}
    run = run_usage({"calls": 30, "questions": 90, "input_tokens": 12_000}, egress, "eu.amazon.nova-lite-v1:0")
    assert run["bedrock"]["usd"] == 0.06 + 0.12 and run["guardrail"]["usd"] == 0.004 and run["decider"]["usd"] == 0
    usage = add_run(add_run(None, run, "analysis", "t1"), run_usage({"calls": 5}, None, None), "re-check", "t2")
    assert usage["total"]["decider"]["requests"] == 35 and usage["total"]["bedrock"]["calls"] == 4
    assert usage["total"]["runs"] == 2 and usage["total"]["usd"] == round(0.184, 6)
    assert usage["total"]["bedrock"]["model"] == "eu.amazon.nova-lite-v1:0"


def test_text_units_round_up_per_1000_characters():
    assert [text_units(n) for n in (0, 1, 1000, 1001)] == [0, 1, 1, 2]
