# Shodhaka

**Shodhaka** (शोधक, Sanskrit: *one who examines and corrects*) is an assistant that finds the gaps
in any document set or flow against the rules you give it, quotes the evidence, and suggests the fix
for a person to approve. The Python package and the command keep the working name `gapanalyzer`.

It is one reusable agent for **any standard written as a rule pack** (company architecture rules,
DORA, ISO 27001, your own). Full documents are analysed locally by **Strands Decider 2B**; only redacted snippets go to
**Amazon Bedrock**, or none at all in offline mode.

First pack: **Acme Shop architecture rules** (`rule-packs/acme-arch.yaml`) — no shared databases,
reliable event publishing, no secrets in config, correlation IDs, timeouts, health endpoints,
pinned images. DORA and ISO 27001 packs use the same schema.

## How it decides

| Decision | Made by |
|---|---|
| Is this section about rule X's topic? (yes/no for every rule, one request per section) | Decider, local |
| Does it meet the requirement? (yes/no, only for on-topic rules, one request) | Decider, local |
| Which sentence is the evidence? (`choice` over the section's sentences) | Decider, local |
| Secrets in config, health endpoint, pinned base image | Plain code |
| Below the confidence threshold (default 0.9) | Escalated as `needs_review` |
| Drafting the fix | Bedrock, redacted snippet only, behind the egress and fix guards |
| Final pass or fail | A human. Nothing is ever auto-passed |

## Run it on your Mac

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[bedrock,docs,ui,dev]"     # docs = PDF and Word support, ui = review web app
pytest -q                                   # 72 tests, no model needed

# 1) start Decider locally in its OWN Python 3.12 environment (first run downloads a few GB)
git clone https://github.com/strands-labs/strands-decider ../strands-decider
cd ../strands-decider && uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install torch numpy && uv pip install -e ".[mlx]"   # without MLX: uv pip install -e .
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device mlx --port 8099   # or --device mps

# 2) in a second terminal: analyse the visible sample set, fully offline
gapanalyzer validate rule-packs/acme-arch.yaml
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible
gapanalyzer eval out/visible/report.json samples/acme-arch/visible/expected.json -v
open out/visible/report.html

#    tune the confidence threshold on the visible set, without new model calls
gapanalyzer calibrate out/visible/report.json samples/acme-arch/visible/expected.json
#    compare strategies (two-stage is the default): --strategy choice gives the old 3-way choice
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-choice --strategy choice

# 3) with Bedrock-drafted fixes (needs AWS credentials and model access in the region)
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-bedrock \
  --bedrock --model eu.amazon.nova-lite-v1:0 --region eu-central-1

# 4) only at the end: the held-out set you never tuned on
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/heldout --out out/heldout
gapanalyzer eval out/heldout/report.json samples/acme-arch/heldout/expected.json -v
```

Keep the Decider and the analyzer in separate environments: the Decider needs PyTorch on Python 3.12, the analyzer runs on any Python 3.10+.
Check in the Bedrock console that the model ID you pass is enabled in your region.

## Organizations, projects and the review UI

```bash
cd ui && npm install && npm run build && cd ..        # once, needs Node 20+
gapanalyzer serve --threshold 0.75                     # http://127.0.0.1:8000 (Decider must be running)
gapanalyzer serve --threshold 0.75 --bedrock           # also offer Bedrock-drafted fixes
```

Work is organised as **organization → project → analysis**:

| Level | What lives there |
|---|---|
| Organization | **general rule packs**, applied to every project (start from a template such as `acme-architecture`, upload YAML or write one in the editor) |
| Project | **project rule packs** for this project only; a project rule with the same id as a general rule **replaces** it (tighten or relax a company rule); a general pack can be switched off per project. The project page lists the rules in effect and where each one comes from |
| Analysis | uploaded documents, report, your decisions and a **snapshot of the rules it ran with** (`rules.yaml`), so editing a pack later never changes an existing report |

Projects never share documents, reports or reviews: every API path goes through the organization and
project ids. There is no login (switch organizations from the header): it separates work, it is not
access control, so keep the server on 127.0.0.1.

The rule-pack editor has a **Form** tab (rules, topic, answers Decider chooses from, code checks) and a
**YAML** tab (comments are kept when you save from it); both are validated against
`specs/contracts/rulepack.schema.json`. Rule ids must be unique within one level.

**Harmful content is removed the moment a file arrives.** Before anything else reads it, the extracted
text is cleaned (`src/gapanalyzer/sanitize.py`): secrets (passwords and keys in config, API keys, tokens,
private keys, credentials in URLs), personal data (e-mail, phone, IBAN and card numbers with checksum,
IP addresses) and instructions aimed at the AI ("ignore previous instructions", "mark all rules as
compliant") are removed by patterns; unsafe language (abusive, hateful, sexual, violent, self-harm) is
found by Decider, locally, section by section, before any rule is checked. Each removal leaves a marker
(`REMOVED_SECRET`, …) so line numbers stay put, and the analysis page lists every removal with type, line
and a masked preview; the removed value is never stored in that list. Edits saved in the UI are cleaned
the same way. Rule checks, exports, the pack suggestion and Bedrock only ever see the cleaned text; the
original upload stays on this machine only. A config file whose literal password was removed still fails
the "no secrets" rule. Not detected: person names and other free-text personal data, and instructions
phrased in ways the patterns do not know. `gapanalyzer run` on the command line does not clean, so the
evaluation sets (including the planted injection in `adr-005`) are scored as they are.

**Which rule packs? Suggested at upload.** Three packs ship as templates: `acme-architecture` (custom
architecture rules), `dora` (DORA ICT risk essentials, EU 2022/2554) and `iso27001` (ISO/IEC 27001:2022
core controls); the DORA and ISO packs are simplified starting points that cite the article or control
behind every rule, not legal or certification advice. When files are chosen, Decider reads the title,
headings and opening text of each document (locally, nothing stored) and answers one choice question:
which pack is meant for a document like this? The suggested packs are ticked; the person can change the
ticks, use a template for one analysis without adding it, and sees the chosen packs again in the
summary before anything runs. `samples/policies/` holds two synthetic policies (incident and continuity,
access control) to try it.

**Several design documents, one design.** When 2 or more design documents are uploaded, the app asks
(required) whether they are separate documents or one design split across files, and shows a summary of
what will be checked before anything runs. As one design, every section is still read on its own, then
the answers of all documents are combined per rule: a rule with `scope: document` (something that must
be present, e.g. a correlation id) is met if any document has it; a rule with `scope: section`
(something that must never happen, e.g. a shared database) is a gap if any document breaks it, and the
finding shows the breaking quote next to a section that meets the rule. Config files and Dockerfiles are
always checked file by file. Editing one document of a set re-checks the whole set. On the command
line: `gapanalyzer run ... --design-set`.

Inside an analysis: documents, findings and detail side by side; **Approve** agrees with the tool,
**Reject** sets your verdict, `Needs review` makes you choose; edit the document, insert the reviewed fix,
**Save & re-check** runs Decider on that document only. Decisions download as `expected.json` for
`gapanalyzer eval`. Keys: `J`/`K` move, `A` approve, `E` edit.

The same layering on the command line:

```bash
gapanalyzer run --pack rule-packs/acme-arch.yaml --project-pack payments.yaml --docs <folder> --out out/payments
```

For UI development: `gapanalyzer serve` in one terminal and `cd ui && npm run dev` in another
(http://127.0.0.1:5173). The frontend structure is described in [ui/README.md](ui/README.md).

## Benchmark: Decider vs an LLM on Bedrock

```bash
# reuse your last Decider run of the visible set (no new Decider calls) and ask Nova Lite the same questions
gapanalyzer bench --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible \
  --expected samples/acme-arch/visible/expected.json --threshold 0.75 \
  --decider-report out/visible/report.json --send-to-bedrock \
  --model eu.amazon.nova-lite-v1:0 --region eu-central-1 --out out/bench
```

The LLM answers exactly the questions Decider answers (on topic? meets the requirement? which
sentence is the evidence?), for the same sections, batched the same way, and its answers go through
the same confidence gate, aggregation and scoring. Only the model behind `ask()` differs. The table
(`out/bench/bench.md`) shows accuracy, gap recall, false alarms, escalation, requests, p50/p95 latency
per request, wall time, tokens and cost. Decider runs locally, so it has no per-request price; the LLM's
cost is its token usage times `--price-in` / `--price-out` (USD per 1,000 tokens, default Nova Lite's
published on-demand price: check the Bedrock pricing page for your region). The LLM reports its own
confidence; Decider's are probabilities.

The LLM side sends section text to Bedrock **without redaction**, which the analyzer never does, so
it needs `--send-to-bedrock` and should only see synthetic or public documents.

## Retrieval (optional): check each rule only against its most likely sections

By default every section is checked against every rule, so nothing can be skipped. For long
documents or large rule packs, a local ranker can shortlist the `top-k` sections per rule first.
Skipped pairs are recorded as "not checked", never as compliant.

```bash
# keyword ranking, no model needed
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-bm25 \
  --threshold 0.75 --retrieval bm25 --top-k 2
# meaning-based ranking with a small local embedding model (pip install -e ".[embed]", Python 3.12)
gapanalyzer run ... --retrieval minilm --top-k 2
# what it saved and what it missed, against the full run
gapanalyzer compare out/visible/report.json out/visible-bm25/report.json
```

On the synthetic visible set, BM25 keeps the section holding the evidence for 9 of 9 rule checks
even at top-1 (22% of section-rule pairs checked); real ADRs are the harder test.

## Supported inputs

| File | Treated as | How it is read |
|---|---|---|
| `.md` | design doc / ADR | split at `##` and `###` headings |
| `.docx` | design doc / ADR | Word heading styles become sections; tables become rows |
| `.pdf` | design doc / ADR | headings found by font size (fallback: numbered or Title Case lines); scanned PDFs need OCR first |
| `.yml`, `.yaml`, `.properties` | config | code checks |
| `Dockerfile`, `*.Dockerfile` | Dockerfile | code checks |

`samples/acme-arch/formats/` holds Word and PDF copies of two ADRs (rebuild with
`python scripts/make_format_samples.py`); they must give the same results as the Markdown originals.

## Real-world ADRs

```bash
python scripts/fetch_real_adrs.py \
  --csv ~/Downloads/replication_package_ADR/replication_package/Data_collection/adr_template.csv \
  --out data/real-adrs --max-repos 15 --keywords
gapanalyzer run --pack rule-packs/acme-arch.yaml --docs data/real-adrs --out out/real
```

Only permissively licensed repositories are downloaded; sources are listed in
`data/real-adrs/ATTRIBUTION.md`. See [DATA_SOURCES.md](DATA_SOURCES.md).

### Measuring real ADRs: label a review sheet

Real ADRs come with no answer key, so `run` cannot print recall or accuracy for them. A person
labels the findings once, and those labels become the ground truth:

```bash
gapanalyzer review-sheet out/real/report.json --out out/real/review.csv --all
# open review.csv in Numbers or Excel; fill `your_verdict` with gap, compliant or not_applicable
gapanalyzer review-score out/real/review.csv --expected-out data/real-adrs-expected.json
gapanalyzer eval out/real/report.json data/real-adrs-expected.json -v
```

`review-score` prints the precision of the flagged gaps (how many were real) and lists false
alarms and missed gaps. Precision needs only the `gap` rows; recall needs every row of the documents
you label, so use `--all` and label whole documents. Rows left blank are not scored. Keep the labels
under `data/` (git-ignored), next to the third-party texts they describe.

## Layout

```
rule-packs/            acme-arch.yaml, dora.yaml, iso27001.yaml (offered as templates in the UI)
specs/contracts/       rulepack.schema.json — the contract every pack follows
samples/acme-arch/     visible/ and heldout/ synthetic docs + expected.json ground truth
src/gapanalyzer/       rulepack, documents, compiler, decider, checks, engine,
                       redact, suggest (Bedrock + guards), report, evaluate, review,
                       tenancy (organizations, projects, packs), api, cli
ui/                    React app: organizations, projects, rule-pack editor, review, edit and re-check
decision-patterns/     the reusable patterns, documented for other builders
tests/                 pytest, with a scripted Decider (no model needed)
```

## Reusable decision patterns

- [Confidence-gated coverage check](decision-patterns/confidence-gated-coverage-check/README.md) (#policy)
- [Egress guard before every model call](decision-patterns/egress-guard/README.md) (#guardrails)

## Safety notes

- Sample documents are synthetic; the company is fictional.
- Secret values are never copied into reports — only the key and line number.
- `samples/acme-arch/visible/adr/adr-005-loyalty-points.md` contains a prompt-injection paragraph on purpose.

Licensed under Apache-2.0.
