# Decision pattern: confidence-gated coverage check

**Pattern tag:** #policy · **Where:** `src/gapanalyzer/compiler.py`, `src/gapanalyzer/engine.py`

Check a piece of text against many rules at once, with a calibrated confidence on every
verdict, and never let the model mark something as "passed".

## The typed question

Each rule in a rule pack becomes one `choice` question. The options are the rule's own, and
each option carries a verdict the code (not the model) acts on:

```yaml
decider:
  question: How does this text describe data access between services?
  options:
    owns-own-data:               {verdict: compliant,      description: each service reads and writes only its own database ...}
    accesses-other-service-data: {verdict: gap,            description: a service reads or writes another service's database ...}
    not-discussed:               {verdict: not_applicable, description: the text does not discuss how services access data}
```

Always include a `not_applicable` option: it gives the model an honest way out for
sections that do not talk about the rule, which keeps confidence on the other options meaningful.

### Two optional fields that matter in practice

- `topic`: a short phrase for the stage-1 "is this section about the rule?" question
  (e.g. "calls from one service to another service or to an external system"). Short topics
  are recognised far more reliably than long generated ones.
- `scope: document`: for rules a design meets once for all (e.g. "messages carry a correlation
  ID"), one section that clearly complies covers the document, and sections that simply do not
  mention it are not gaps. Default `section`: every section must comply.

On the visible sample set this took exact accuracy from 0.579 (one 3-way choice, threshold 0.9)
to 0.947 (two-stage yes/no, document scope, threshold 0.75) with zero false alarms.

## The wiring

1. **One request per section, every rule in it.** The section is the `state`; each applicable
   rule is a question keyed by its rule id. Decider encodes the state once and each extra rule
   costs only its own question tokens.
2. **Gate in code.**
   - a `gap` answer at confidence ≥ threshold → **gap**
   - a `gap` answer below threshold → **needs_review** (escalate to an LLM or a human)
   - a `compliant` answer at ≥ threshold → **covered**, still pending human sign-off
   - otherwise → **not_applicable**
3. **Evidence by choice.** For a gap, a second `choice` question offers the section's
   sentences as options: "Which sentence is the strongest evidence that ...?" The report
   quotes the chosen sentence.

## How to reuse it

- Write your rules as YAML that follows `specs/contracts/rulepack.schema.json`.
- Call `analyze(pack, documents, decider, threshold=0.9)` from `gapanalyzer.engine`.
- Start the threshold at 0.9 and tune it on documents with planted gaps, then confirm on a
  held-out set you never tuned on.

## What it costs and what it does not do

- Decider is weaker on hard multi-step reasoning, so keep each rule question short and specific.
- It classifies; it does not explain. Explanations and fixes come from Bedrock, on redacted snippets only.
- Prompt injection inside a document can sway a classifier but cannot change the policy: pass/fail is set in code.
