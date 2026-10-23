# Using Shodhaka

## Organizations, projects and analyses

```bash
shodhaka serve                    # http://127.0.0.1:8000, Decider must be running on :8099
shodhaka serve --bedrock          # also offer Bedrock-drafted fixes
```

| Level | What lives there |
|---|---|
| Organization | General rule packs, applied to every project. Start from a template, upload YAML or write one in the editor. |
| Project | Project rule packs. A project rule with the same id as a general rule replaces it; a general pack can be switched off per project. The project page lists the rules in effect and where each one comes from. |
| Analysis | Uploaded documents, the report, your decisions and a snapshot of the rules it ran with (`rules.yaml`), so editing a pack later never changes an existing report. |

Projects never share documents, reports or reviews. There is no login: organizations separate work,
they are not access control, so keep the server on 127.0.0.1.

The pack editor has a Form tab and a YAML tab (comments are kept when you save from YAML). Both are
validated against `src/shodhaka/rules/rulepack.schema.json`. Rule ids must be unique within one level.

### At upload

1. **Cleaning.** Secrets, personal data (e-mail, phone, IBAN and card numbers with checksum, IP
   addresses) and instructions aimed at the AI are removed by patterns; unsafe language is found by
   Decider, section by section. Each removal leaves a marker such as `REMOVED_SECRET`, so line numbers
   stay put. The analysis page lists every removal with a masked preview. See [SECURITY.md](../SECURITY.md).
2. **Pack suggestion.** Decider reads the title, headings and opening text of each file and answers one
   `choice` question: which pack is meant for a document like this? The suggested packs are ticked;
   you can change them.
3. **One design or separate documents.** With two or more design documents, you must say how they
   relate. As one design, rules with `scope: document` are met if any document meets them, and rules
   with `scope: section` are a gap if any document breaks them. Config files and Dockerfiles are always
   checked file by file.
4. **Summary.** You see exactly what will be checked, and how, before anything runs.

### Reviewing

Documents, findings and detail sit side by side. **Approve** agrees with the tool, **Reject** sets your
verdict, and `needs_review` makes you choose. Edit the document, insert the reviewed fix, and
**Save & re-check** runs Decider on that document only. Your decisions download as `expected.json`.
Keys: `J`/`K` move, `A` approve, `E` edit.

## Command line

```bash
shodhaka validate rule-packs/acme-arch.yaml
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible
shodhaka eval out/visible/report.json samples/acme-arch/visible/expected.json -v
open out/visible/report.html

# layered packs, like the UI
shodhaka run --pack rule-packs/acme-arch.yaml --project-pack payments.yaml --docs <folder> --out out/payments
# several documents as one design
shodhaka run --pack rule-packs/acme-arch.yaml --docs <folder> --out out/design --design-set
# draft fixes with Bedrock (redacted snippets only)
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-bedrock --bedrock
```

With a guardrail created in the Bedrock console, every fix call also goes through it:

```bash
shodhaka run ... --bedrock --guardrail-id <guardrail id> --guardrail-version 1
shodhaka serve --bedrock --guardrail-id <guardrail id> --guardrail-version 1
# or once per terminal: export SHODHAKA_GUARDRAIL_ID=<id> SHODHAKA_GUARDRAIL_VERSION=1
```

If the guardrail blocks a call, that finding gets the rule's fix hint instead and the report's
`egress.guardrail_interventions` counts it.

`shodhaka run` does not clean documents, so the evaluation sets (including the planted injection in
`adr-005`) are scored as they are.

### Choosing the threshold

Every per-section answer is stored in the report, so other thresholds can be scored without calling
the model again:

```bash
shodhaka calibrate out/visible/report.json samples/acme-arch/visible/expected.json
```

Tune on `visible/`, then run `heldout/` once at the end.

### Benchmark: Decider vs an LLM on Bedrock

```bash
shodhaka bench --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible \
  --expected samples/acme-arch/visible/expected.json --out out/bench/visible --send-to-bedrock
```

The LLM gets exactly the questions Decider gets, for the same sections, batched the same way, and its
answers go through the same gate and scoring. Cost is token usage times `--price-in` / `--price-out`
(USD per 1,000 tokens; the defaults are Nova Lite's on-demand price). `--decider-report` reuses an
earlier Decider run; `--skip-llm` runs Decider only.

The LLM side sends section text to Bedrock **without redaction**, so it needs `--send-to-bedrock` and
should only see synthetic or public documents.

### Rubric LLM-as-judge for fixes and evidence

Verdicts are scored against labels; the generated text is not. A second model from another vendor grades each
gap's fix and evidence quote from 1 to 5 on five criteria: resolves the gap, grounded in the rule
and evidence, actionable, safe, and whether the quote really shows the problem.

```bash
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-bedrock --bedrock
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-offline
shodhaka judge out/visible-bedrock/report.json out/visible-offline/report.json \
  --pack rule-packs/acme-arch.yaml --model openai.gpt-oss-120b-1:0 --region <region> --out out/judge
```

This compares Nova Lite's fixes with the rule owner's own fix hints. The judge sees the redacted
evidence and fix only. Results land in `out/judge/judge.md`, `judge.json` and `judge.svg`.

### Retrieval (optional)

By default every section is checked against every rule. For long documents a local ranker can
shortlist the top-k sections per rule first; skipped pairs are recorded as "not checked", never as
compliant.

```bash
shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible-bm25 --retrieval bm25 --top-k 2
shodhaka run ... --retrieval minilm --top-k 2      # pip install -e ".[embed]"
shodhaka compare out/visible/report.json out/visible-bm25/report.json
```

## Supported inputs

| File | Treated as | How it is read |
|---|---|---|
| `.md` | design doc / ADR / policy | split at `##` and `###` headings |
| `.docx` | design doc / ADR / policy | Word heading styles become sections; tables become rows |
| `.pdf` | design doc / ADR / policy | headings by font size (fallback: numbered or Title Case lines); scanned PDFs need OCR first |
| `.yml`, `.yaml`, `.properties` | config | code checks |
| `Dockerfile`, `*.Dockerfile` | Dockerfile | code checks |

`samples/acme-arch/formats/` holds Word and PDF copies of two ADRs (rebuild with
`python scripts/make_format_samples.py`); they give the same results as the Markdown originals.

## Real documents

```bash
python scripts/fetch_project_docs.py              # 4 open-source projects into data/projects
python scripts/fetch_real_adrs.py --csv <adr_template.csv> --out data/real-adrs --max-repos 15 --keywords
shodhaka run --pack rule-packs/acme-arch.yaml --docs data/projects/piggymetrics --out out/piggymetrics
```

Only permissively licensed repositories are downloaded; each folder gets an `ATTRIBUTION.md`.

Real documents have no answer key, so label one:

```bash
shodhaka review-sheet out/real/report.json --out out/real/review.csv --all
# fill `your_verdict` with gap, compliant or not_applicable
shodhaka review-score out/real/review.csv --expected-out data/real-adrs-expected.json
shodhaka eval out/real/report.json data/real-adrs-expected.json -v
```

`review-score` prints the precision of the flagged gaps and lists false alarms and missed gaps. Recall
needs every row of the documents you label, so use `--all` and label whole documents.
