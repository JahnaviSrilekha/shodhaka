# Decision pattern: confidence-gated coverage check

**Pattern tag:** #policy

Check a document against many rules with Strands Decider 2B. The model answers small yes/no
questions; plain code turns the answers into a verdict, and nothing is passed automatically.

`coverage_check.py` is the whole pattern in about 110 lines of standard-library Python. Copy it
into your project. Shodhaka uses the same logic in `src/shodhaka/rules/compiler.py` (questions)
and `src/shodhaka/analysis/engine.py` (`gate`).

```bash
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099
python run_example.py            # runs example.json against Decider
python -m pytest -q              # no Decider needed (fake answers)
```

## The typed questions

For every section of the document:

1. **On topic?** One request, one yes/no per rule: "Does this section talk about
   *which database, schema or tables a service owns, reads or writes*?"
2. **Compliant?** One more request, only for the rules that are on topic: "Does what this
   section describes meet this requirement: *Each microservice owns its data*?"

The section is the `state`, the rules are the questions, keyed by rule id. Decider reads the
section once per request, so each extra rule costs only its own question.

A rule needs three things:

```python
Rule(id="ARCH-01",
     topic="which database, schema or tables a service owns, reads or writes",  # short!
     requirement="Each microservice owns its data. No service reads or writes another service's database.",
     scope="section")
```

Keep `topic` to a short noun phrase. Long, generated topics were recognised far less reliably.

## The gate (in code, not in the model)

| Answers across sections | Status |
|---|---|
| a "breaks it" at confidence ≥ threshold | `gap` |
| a "breaks it" below the threshold | `needs_review` (a person decides) |
| a "meets it" at ≥ threshold | `covered`, still waiting for sign-off |
| a "meets it" below the threshold | `needs_review` |
| no section on topic | `not_applicable` |

`scope` says how sections combine:

- `section` (the default) for prohibitions such as "never share a database": any section that
  breaks it makes a gap.
- `document` for things that must be present somewhere, such as "messages carry a correlation
  ID": one section that clearly meets it covers the document, and sections that do not mention
  it are not gaps.

## Why two yes/no questions

On Shodhaka's tuning set, one three-way `choice` per rule and section reached 58% exact
accuracy. Two yes/no questions reached 63%, and short topics plus `scope: document` took it to
90%, with no false alarms. Off-topic sections stop voting on rules they never discuss.

## Choosing the threshold

Start at 0.75. Keep every per-section answer, so you can re-score other thresholds offline
(`shodhaka calibrate` does this), tune on documents with planted gaps, then confirm once on a
held-out set you never tuned on.

## Limits

- Decider classifies; it does not explain. Write fixes with an LLM, on redacted text.
- It is weaker at multi-step reasoning, so keep each question about one thing.
- Text inside a document can try to sway the model, but it cannot change the policy: the
  verdict is decided by the gate, and the state tells the model the section is data.
