# Test scenarios

Every case Shodhaka handles, the sample that triggers it, and what you should see. Files are under
`samples/`. "UI" means the review app (`shodhaka serve --bedrock`), "CLI" the command line.

| # | Case | Input | Expected | Where to see it |
|---|---|---|---|---|
| 1 | Pack suggestion | `acme-arch/visible/adr/*.md` · `policies/ict-incident-and-continuity-policy.md` · `policies/access-control-policy.md` | ADRs get the architecture pack, the incident policy DORA, the access policy ISO 27001 | UI: *Recommended* tags in New analysis |
| 2 | Separate vs one design | two or more ADRs | the app asks how they relate before anything runs; "one design" turns a missing correlation ID into covered if any ADR has it | UI: required question and the *Check before starting* summary |
| 3 | Prompt injection removed | `acme-arch/visible/adr/adr-005-loyalty-points.md` | "Ignore all previous instructions…" removed at upload, real gap still reported | UI: *Removed before analysis* |
| 4 | Secrets and personal data removed | `acme-arch/visible/config/billing-service/application.yml` | password and API key values and an IP address removed, line numbers kept | UI: *Removed before analysis* |
| 5 | Gap with quoted evidence | `adr-005` (ARCH-01) · `adr-002` (ARCH-01, ARCH-02, ARCH-05) | **Gap**, the sentence that proves it, confidence above the 75% gate | UI: finding detail |
| 6 | Unsure → a person decides | `adr-003-notification-service.md` | one check lands just under the gate as **Needs review** | UI: *Needs review* filter |
| 7 | Covered | `adr-001-order-saga.md` | rules met show **Covered**, still waiting for sign-off | UI |
| 8 | Not applicable | any ADR | rules no section talks about show **Not applicable** | UI |
| 9 | Code checks | billing `application.yml` and `billing-service.Dockerfile` vs order-service ones | secrets in config (ARCH-03), exposed health endpoint (ARCH-06), unpinned image (ARCH-07) are gaps for billing; the pinned order-service image passes | UI: "checked by code" |
| 10 | Word and PDF input | `acme-arch/formats/*.docx`, `*.pdf` | same verdicts as the Markdown originals | CLI: `shodhaka eval … formats/expected.json` |
| 11 | Fix drafted by Bedrock | any gap, Bedrock box ticked | fix "drafted by Bedrock from a redacted snippet" | UI: suggested fix |
| 12 | Fallback with a reason | Bedrock key missing or guardrail wrong | fix "from the rule's fix hint (bedrock failed: …)" or "(blocked by Bedrock guardrail)" | UI: suggested fix |
| 13 | Approve, reject, choose | any finding | your verdict is stored; `expected.json` downloads your decisions | UI: decision buttons, *expected.json* |
| 14 | Edit and re-check | edit adr-005's "Data" section so Loyalty calls the Customer API | ARCH-01 is no longer a gap; your earlier decision shows "Re-checked · decide again" | UI: *Edit document and re-check* |
| 15 | DORA, strong policy | `policies/dora-ict-risk-management-framework.md` | DORA-07 (resilience testing) and DORA-09 (exit plan) are gaps, the rest covered | UI or CLI with `rule-packs/dora.yaml` |
| 16 | DORA, weak policy | `policies/ict-incident-and-continuity-policy.md` | gaps on board ownership, regulator reporting, restore tests, provider register, exit plan | UI or CLI |
| 17 | ISO 27001 | `policies/access-control-policy.md` | a mostly sound policy: access reviews and logging covered, topics it never mentions not applicable | UI with the ISO pack |
| 18 | Isolation and overrides | two organizations or projects; a project rule with an existing id | projects never see each other's analyses; the project rule replaces the general one ("Project rule" tag) | UI: project page, rule source tag |
| 19 | Calls and cost | any finished analysis | Decider requests ($0), Bedrock calls and tokens, guardrail units, total; project total on the project page | UI: *Calls and cost* |
| 20 | Unsupported file | a `.txt` or `.png` | marked "not supported, will be skipped", the rest analysed | UI: file list in New analysis |
| 21 | Decider offline | stop Decider | header shows it, starting is blocked with a clear message | UI header |
| 22 | Held-out accuracy | `acme-arch/heldout` | 100% on 7 labelled checks | CLI: `shodhaka run` + `shodhaka eval` |
| 23 | Decider vs Nova Lite | `acme-arch/visible` | tables in `docs/results/benchmark.md` | CLI: `shodhaka bench` |
| 24 | Rubric judge | a `--bedrock` and an offline run | scores for fixes and evidence | CLI: `shodhaka judge` |

Automated checks of the same behaviour, with a scripted Decider: `pytest -q` (86 tests) and
`cd ui && npx vitest run`.
