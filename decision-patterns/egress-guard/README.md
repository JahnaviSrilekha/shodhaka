# Decision pattern: egress guard before every model call

**Pattern tag:** #guardrails · **Where:** `src/gapanalyzer/suggest.py` (`EgressGuard`)

A Strands `InterventionHandler.before_model_call` that blocks any prompt to a hosted LLM while
it still contains identifying details, and logs the bytes of every prompt it lets through.

## The checks, in order

1. **Deterministic:** the redactor's own originals (hosts, IPs, JDBC URLs, keys, e-mails) or any
   still-matching sensitive pattern → `Deny`.
2. **Decider (yes/no):** "Does this text still contain identifying details such as real hostnames,
   IP addresses, credentials, e-mail addresses or person names?" — catches what regex cannot,
   such as a person's name. P(yes) ≥ 0.8 → `Deny`.
3. Otherwise `Proceed`, and append `{finding, bytes, text}` to the egress log shown in the report.

## How to reuse it

```python
from strands import Agent
guard = EgressGuard(redactor, decider, log, finding_id="F-1")
agent = Agent(model=..., interventions=[guard])
```

Redact before you build the prompt; the guard is the second line of defence, not the first.
