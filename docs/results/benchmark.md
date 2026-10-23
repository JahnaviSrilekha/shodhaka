# Decider 2B vs Nova Lite

Same questions, same sections, same confidence gate (0.75) and scoring; only the model behind `ask()`
differs. Decider 2B ran locally on an Apple-silicon Mac; Nova Lite ran on Amazon Bedrock in
eu-central-1 (`eu.amazon.nova-lite-v1:0`). Run on 23 October 2026 with `shodhaka bench`.

## Tuning set (`samples/acme-arch/visible`, 19 labelled checks)

| Metric | Strands Decider 2B (local) | Nova Lite (Bedrock) |
|---|---|---|
| Exact accuracy | 89.5% | 89.5% |
| Gap recall (gap only) | 88.9% | 88.9% |
| Gap recall (gap or review) | 88.9% | 88.9% |
| False alarms | 0.0% | 11.1% |
| Escalated to a person | 5.3% | 0.0% |
| Requests | 34 | 34 |
| Latency p50 per request (ms) | 736 | 731 |
| Latency p95 per request (ms) | 1,138 | 919 |
| Wall time (s) | 42.1 | 26.5 |
| Input tokens | 14,017 | 13,798 |
| Output tokens | – | 2,496 |
| Cost, total (USD) | 0 | 0.001427 |
| Cost per 1,000 requests (USD) | 0 | 0.042 |

## Held-out set (`samples/acme-arch/heldout`, 7 labelled checks, never used for tuning)

| Metric | Strands Decider 2B (local) | Nova Lite (Bedrock) |
|---|---|---|
| Exact accuracy | 100.0% | 100.0% |
| Gap recall | 100.0% | 100.0% |
| False alarms | 0.0% | 0.0% |
| Escalated to a person | 0.0% | 0.0% |
| Requests | 9 | 9 |
| Latency p50 per request (ms) | 748 | 847 |
| Latency p95 per request (ms) | 4,521 (first request, model warming up) | 1,324 |
| Wall time (s) | 10.1 | 8.3 |
| Cost per 1,000 requests (USD) | 0 | 0.042 |

## Reading it

- Accuracy and median latency are a tie.
- They are wrong in different ways. Where Decider was unsure, the gate sent the case to a person.
  Nova Lite answered it confidently and wrongly, which became a false alarm.
- Nova Lite finished the batch faster and costs very little, but every section leaves the machine.
  Decider costs nothing per call and keeps documents local.
- These are small synthetic sets: a sanity check, not a leaderboard.

Reproduce:

```bash
shodhaka bench --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible \
  --expected samples/acme-arch/visible/expected.json --out out/bench/visible --send-to-bedrock
```
