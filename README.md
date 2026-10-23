# Shodhaka

**Shodhaka** (शोधक, Sanskrit for *one who examines and corrects*) checks design documents, policies
and config files against a rulebook, quotes the evidence for every gap and suggests a fix that a person
approves.

- **Any rulebook.** Rules are YAML (a *rule pack*). Three ship as templates: Acme architecture rules,
  DORA ICT-risk essentials and ISO/IEC 27001:2022 core controls.
- **Strands Decider 2B makes the decisions, locally.** Which pack fits a document, whether a section is
  about a rule, whether it meets it, and which sentence is the evidence.
- **Amazon Bedrock only writes the fix text**, from redacted snippets, behind two guards.
- **A person signs off on everything.** Nothing is passed automatically.

| Decision | Made by |
|---|---|
| Is this section about rule X? (yes/no for every rule, one request per section) | Decider 2B, local |
| Does it meet the requirement? (yes/no, only for the rules it is about) | Decider 2B, local |
| Which sentence is the evidence? (`choice` over the section's sentences) | Decider 2B, local |
| Secrets in config, health endpoint, pinned base image | Plain code |
| Below the confidence threshold (default 0.75) | Sent to a person as `needs_review` |
| Drafting the fix | Nova Lite on Bedrock, redacted snippet only |
| Final pass or fail | A person |

## Results

On the synthetic sample sets, gate at 0.75 (full tables in [docs/results/benchmark.md](docs/results/benchmark.md)):

| | Decider 2B (local) | Nova Lite (Bedrock) |
|---|---|---|
| Exact agreement, tuning set (19 checks) | 89.5% | 89.5% |
| False alarms | 0% | 11.1% |
| Sent to a person | 5.3% | 0% |
| Held-out set (7 checks) | 100% | 100% |
| Median latency per request | 736 ms | 731 ms |
| Cost per 1,000 requests | $0 | $0.042 |

## Quick start

You need Python 3.10+, Node 20+, and Strands Decider in its own Python 3.12 environment.

```bash
# 1) Decider (first run downloads a few GB)
git clone https://github.com/strands-labs/strands-decider ../strands-decider
cd ../strands-decider && uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install torch numpy && uv pip install -e ".[mlx]"
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device mlx --port 8099

# 2) Shodhaka, in a second terminal
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[bedrock,docs,ui,dev]"
pytest -q                                   # no model needed
cd ui && npm install && npm run build && cd ..
shodhaka serve                              # http://127.0.0.1:8000
shodhaka serve --bedrock                    # also draft fixes with Nova Lite
```

Then register an organization, add a template pack, create a project and upload a few files from
`samples/`. From the command line:

```bash
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible
shodhaka eval out/visible/report.json samples/acme-arch/visible/expected.json -v
```

More commands (calibration, design sets, the benchmark, retrieval, real ADRs) are in
[docs/guide.md](docs/guide.md).

## Project layout

```
src/shodhaka/
  decider.py            client for the local Decider server (+ a scripted test double)
  rules/                rule packs: loading and schema, rules -> typed questions, checks done in code
  documents/            reading .md/.docx/.pdf/config/Dockerfile, sections, cleaning, redaction
  analysis/             engine and confidence gate, retrieval, pack suggestion, Bedrock fixes, reports
  evaluation/           scoring against labels, review sheets, Decider vs LLM benchmark
  web/                  FastAPI app and the organization / project workspace
  cli.py                the `shodhaka` command
ui/                     React review app (see ui/README.md)
rule-packs/             acme-arch, dora, iso27001
samples/                synthetic documents with expected.json answer keys
decision-patterns/      reusable patterns, runnable on their own
docs/                   guide, results, demo script
tests/
```

How the pieces fit together: [ARCHITECTURE.md](ARCHITECTURE.md). What leaves the machine and what
does not: [SECURITY.md](SECURITY.md).

## Reusable decision patterns

- [Confidence-gated coverage check](decision-patterns/confidence-gated-coverage-check/) (#policy):
  about 110 lines, standard library only, with an example and tests.
- [Egress guard before every model call](decision-patterns/egress-guard/README.md) (#guardrails).

## Notes

- All sample documents are synthetic and the company is fictional.
  `samples/acme-arch/visible/adr/adr-005-loyalty-points.md` contains a prompt injection on purpose.
- The DORA and ISO packs are simplified starting points, not legal or certification advice.
- Third-party documents used for testing are downloaded into `data/` (git-ignored), see
  [DATA_SOURCES.md](DATA_SOURCES.md).

Licensed under Apache-2.0.
