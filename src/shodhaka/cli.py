"""Command line: validate a pack, run an analysis, score it against ground truth.

    shodhaka validate rule-packs/acme-arch.yaml
    shodhaka run --pack rule-packs/acme-arch.yaml --docs samples/acme-arch/visible --out out/visible
    shodhaka run ... --bedrock                      # draft fixes with Bedrock (redacted snippets only)
    shodhaka run --pack general.yaml --project-pack payments.yaml --docs ...   # layered like the UI
    shodhaka serve                                  # organisations, projects and review UI on :8000
    shodhaka eval out/visible/report.json samples/acme-arch/visible/expected.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shodhaka.analysis.engine import DEFAULT_THRESHOLD, analyze
from shodhaka.analysis.fixes import DEFAULT_MODEL, DEFAULT_REGION, FixWriter, add_fixes
from shodhaka.analysis.report import write_html, write_json
from shodhaka.analysis.retrieval import METHODS, make_ranker
from shodhaka.decider import DEFAULT_URL, DeciderUnavailable, HttpDecider
from shodhaka.documents.model import discover
from shodhaka.evaluation.scoring import calibrate, compare, evaluate
from shodhaka.rules.pack import RulePackError, load_pack


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        pack = load_pack(args.pack)
    except RulePackError as exc:
        print(exc, file=sys.stderr)
        return 1
    methods = {"decider": 0, "code": 0}
    for rule in pack.rules:
        methods[rule.method] += 1
    print(f"OK {pack.pack} v{pack.version}: {len(pack.rules)} rules "
          f"({methods['decider']} Decider, {methods['code']} code)")
    return 0


def _layered_pack(general: list[str], project: list[str]):
    """One --pack is used as is; several packs (and --project-pack) are layered like in the UI:
    project rules replace general rules with the same id."""
    from shodhaka.rules.pack import compose, parse, parse_yaml

    if len(general) == 1 and not project:
        return load_pack(general[0]), {}
    read = lambda paths: [parse_yaml(Path(p).read_text(encoding="utf-8")) for p in paths]  # noqa: E731
    combined, sources = compose(read(general), read(project))
    return parse(combined), sources


def cmd_run(args: argparse.Namespace) -> int:
    try:
        pack, sources = _layered_pack(args.pack, args.project_pack or [])
    except RulePackError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not Path(args.docs).is_dir():
        print(f"folder not found: {args.docs}"
              + (" (download real ADRs first: python scripts/fetch_real_adrs.py ...)" if "real-adrs" in args.docs else ""),
              file=sys.stderr)
        return 1
    documents = discover(args.docs)
    if not documents:
        print(f"no reviewable documents under {args.docs} (looked for .md .pdf .docx .yml .yaml .properties Dockerfile)",
              file=sys.stderr)
        return 1
    decider = HttpDecider(args.decider_url)
    try:
        print(decider.health().get("checkpoint", "decider ready"), file=sys.stderr)
    except DeciderUnavailable as exc:
        print(exc, file=sys.stderr)
        return 2
    ranker = make_ranker(args.retrieval)
    report = analyze(pack, documents, decider, threshold=args.threshold, strategy=args.strategy,
                     ranker=ranker, top_k=args.top_k, mode="design-set" if args.design_set else "per-document")
    writer = FixWriter(decider, args.model, args.region) if args.bedrock else None
    report = add_fixes(report, pack, writer)
    for finding in report["findings"]:
        if sources:
            finding["rule_source"] = sources.get(finding["rule_id"])
    report["decider"] = decider.stats.as_dict()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(report, out / "report.json")
    write_html(report, out / "report.html")
    s = report["summary"]
    print(f"{s['gap']} gaps, {s['needs_review']} need review, {s['covered']} covered, "
          f"{s['not_applicable']} not applicable · {report['decider']['calls']} Decider calls "
          f"(p50 {report['decider']['latency_ms_p50']} ms) · {report['egress']['bytes_sent']} bytes to Bedrock")
    rt = report["retrieval"]
    if rt["method"] != "none":
        print(f"retrieval {rt['method']} top-{rt['top_k']}: checked {rt['pairs_checked']} of {rt['pairs_total']} section-rule pairs")
    print(f"report: {out / 'report.html'}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = evaluate(report, args.expected)
    rows = result.pop("rows")
    print(json.dumps(result, indent=2))
    if args.verbose:
        for r in rows:
            mark = "ok " if (r["expected"], r["status"]) in {("gap", "gap"), ("compliant", "covered"), ("not_applicable", "not_applicable")} else "XX "
            print(f"{mark}{r['rule']:8} {r['file']:45} expected={r['expected']:15} got={r['status']:15} conf={r['confidence']:.2f}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = calibrate(report, args.expected)
    print(f"{'threshold':>9} {'recall':>7} {'recall+review':>13} {'false alarms':>12} {'accuracy':>8} {'escalated':>9}")
    for r in rows:
        print(f"{r['threshold']:>9.2f} {r['gap_recall_strict']:>7} {r['gap_recall_with_review']:>13} "
              f"{r['false_alarm_rate']:>12} {r['exact_accuracy']:>8} {r['escalation_rate']:>9}")
    print("Pick the highest accuracy with 0 false alarms, then confirm it ONCE on the held-out set.")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    full = json.loads(Path(args.full).read_text(encoding="utf-8"))
    short = json.loads(Path(args.retrieval).read_text(encoding="utf-8"))
    print(json.dumps(compare(full, short), indent=2))
    return 0


def cmd_review_sheet(args: argparse.Namespace) -> int:
    from shodhaka.evaluation.review import write_sheet
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    count = write_sheet(report, Path(args.out), include_not_applicable=args.all)
    print(f"{count} rows written to {args.out}. Fill the 'your_verdict' column with gap, compliant or not_applicable,")
    print(f"then run: shodhaka review-score {args.out} --expected-out <file>.json")
    return 0


def cmd_review_score(args: argparse.Namespace) -> int:
    from shodhaka.evaluation.review import read_sheet, score, to_expected
    filled, problems = read_sheet(Path(args.sheet))
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
    if not filled:
        print("no rows have a your_verdict value yet", file=sys.stderr)
        return 1
    print(json.dumps(score(filled), indent=2))
    if args.expected_out:
        Path(args.expected_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.expected_out).write_text(json.dumps(to_expected(filled, args.pack), indent=2), encoding="utf-8")
        print(f"ground truth for {len(filled)} rows written to {args.expected_out}; "
              f"score the full report with: shodhaka eval <report.json> {args.expected_out} -v")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    import time as _time

    from shodhaka.evaluation.bench import BedrockDecider, cost, summarise, table, write
    from shodhaka.evaluation.scoring import rescore

    if not args.skip_llm and not args.send_to_bedrock:
        print("The LLM side sends section text to Bedrock WITHOUT redaction (the analyzer never does).\n"
              "Run it on synthetic or public documents only, and confirm with --send-to-bedrock "
              "(or use --skip-llm).", file=sys.stderr)
        return 1
    try:
        pack, _ = _layered_pack(args.pack, args.project_pack or [])
    except RulePackError as exc:
        print(exc, file=sys.stderr)
        return 1
    documents = discover(args.docs)
    if not documents:
        print(f"no reviewable documents under {args.docs}", file=sys.stderr)
        return 1
    mode = "design-set" if args.design_set else "per-document"
    out = Path(args.out)
    rows = []

    if args.decider_report:  # reuse an earlier Decider run (no new calls), re-gated at this threshold
        report = rescore(json.loads(Path(args.decider_report).read_text(encoding="utf-8")), args.threshold)
        seconds = None
    else:
        decider = HttpDecider(args.decider_url)
        try:
            decider.health()
        except DeciderUnavailable as exc:
            print(exc, file=sys.stderr)
            return 2
        started = _time.perf_counter()
        report = analyze(pack, documents, decider, threshold=args.threshold, mode=mode)
        seconds = _time.perf_counter() - started
        report["decider"] = decider.stats.as_dict()
    (out / "decider").mkdir(parents=True, exist_ok=True)
    write_json(report, out / "decider" / "report.json")
    row = summarise("Strands Decider 2B (local)", report, evaluate(report, args.expected), seconds or 0.0, 0.0)
    if seconds is None:
        row["wall_seconds"] = None
    rows.append(row)

    if not args.skip_llm:
        llm = BedrockDecider(args.model, args.region)
        started = _time.perf_counter()
        try:
            llm_report = analyze(pack, documents, llm, threshold=args.threshold, mode=mode)
        except Exception as exc:  # noqa: BLE001 (credentials, model access, region)
            print(f"Bedrock call failed: {type(exc).__name__}: {exc}\n"
                  f"Check AWS credentials and that {args.model} is enabled in {args.region}.", file=sys.stderr)
            return 2
        seconds = _time.perf_counter() - started
        llm_report["decider"] = llm.stats.as_dict()
        (out / "llm").mkdir(parents=True, exist_ok=True)
        write_json(llm_report, out / "llm" / "report.json")
        usd = cost(llm_report["decider"], args.price_in, args.price_out)
        rows.append(summarise(f"{args.model} (Bedrock)", llm_report, evaluate(llm_report, args.expected), seconds, usd))

    meta = {"docs": args.docs, "documents": len(documents), "expected": args.expected, "threshold": args.threshold,
            "mode": mode, "llm_model": args.model, "region": args.region,
            "price_per_1k_tokens": {"input": args.price_in, "output": args.price_out}}
    write(out, rows, meta)
    print(table(rows))
    print(f"\nwritten: {out / 'bench.md'} and {out / 'bench.json'}")
    if len(rows) == 2 and rows[1].get("unparsed_replies"):
        print(f"note: {rows[1]['unparsed_replies']} LLM replies could not be parsed and were counted as unsure (0.5)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from shodhaka.web.api import create_app
    except ImportError:
        print('the UI server needs extra packages: pip install -e ".[ui]"', file=sys.stderr)
        return 1
    ui_dist = Path(args.ui_dist)
    if not (ui_dist / "index.html").exists():
        print(f"no built UI in {ui_dist}: run `cd ui && npm install && npm run build`, "
              f"or use `npm run dev` (http://127.0.0.1:5173) during development", file=sys.stderr)
    bedrock = {"model_id": args.model, "region": args.region} if args.bedrock else None
    app = create_app(args.workspace, args.pack_dir, lambda: HttpDecider(args.decider_url),
                     threshold=args.threshold, bedrock=bedrock, ui_dist=ui_dist)
    print(f"Shodhaka UI on http://{args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shodhaka", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a rule pack against the schema")
    v.add_argument("pack")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="analyse documents against a rule pack")
    r.add_argument("--pack", required=True, action="append",
                   help="rule pack; repeat to combine several general packs")
    r.add_argument("--project-pack", action="append",
                   help="project-specific pack; its rules replace general rules with the same id")
    r.add_argument("--docs", required=True)
    r.add_argument("--out", default="out")
    r.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    r.add_argument("--strategy", choices=["two-stage", "choice"], default="two-stage",
                   help="two-stage: yes/no relevance then yes/no compliance (default); choice: one 3-way choice")
    r.add_argument("--retrieval", choices=METHODS, default="none",
                   help="shortlist sections per rule before Decider: none (check all, default), bm25, minilm")
    r.add_argument("--top-k", type=int, default=3, help="sections per rule when --retrieval is set")
    r.add_argument("--design-set", action="store_true",
                   help="the design documents are one design split across files: a 'document'-scope rule is met if "
                        "any document meets it, a 'section'-scope rule is a gap if any document breaks it")
    r.add_argument("--decider-url", default=DEFAULT_URL)
    r.add_argument("--bedrock", action="store_true", help="draft fixes with Bedrock (default: offline, rule hints)")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--region", default=DEFAULT_REGION)
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("eval", help="score a report against expected.json")
    e.add_argument("report")
    e.add_argument("expected")
    e.add_argument("-v", "--verbose", action="store_true")
    e.set_defaults(func=cmd_eval)

    logging.basicConfig(level=logging.WARNING, format="warning: %(message)s")
    c = sub.add_parser("calibrate", help="compare confidence thresholds on an existing report (no model calls)")
    c.add_argument("report")
    c.add_argument("expected")
    c.set_defaults(func=cmd_calibrate)

    k = sub.add_parser("compare", help="what retrieval saved and missed, against a full (no-retrieval) run")
    k.add_argument("full", help="report.json from a run without --retrieval")
    k.add_argument("retrieval", help="report.json from a run with --retrieval")
    k.set_defaults(func=cmd_compare)

    rs = sub.add_parser("review-sheet", help="write a CSV for a person to label the findings of a report")
    rs.add_argument("report")
    rs.add_argument("--out", default="review.csv")
    rs.add_argument("--all", action="store_true", help="include 'not applicable' rows (needed to measure recall)")
    rs.set_defaults(func=cmd_review_sheet)

    sc = sub.add_parser("review-score", help="precision from a filled review sheet; optionally write expected.json")
    sc.add_argument("sheet")
    sc.add_argument("--expected-out", help="write the labels as an expected.json for shodhaka eval")
    sc.add_argument("--pack", default="acme-architecture")
    sc.set_defaults(func=cmd_review_score)

    b = sub.add_parser("bench", help="same rule checks by Decider and by an LLM on Bedrock: accuracy, latency, cost")
    b.add_argument("--pack", required=True, action="append")
    b.add_argument("--project-pack", action="append")
    b.add_argument("--docs", required=True)
    b.add_argument("--expected", required=True, help="expected.json for these documents")
    b.add_argument("--out", default="out/bench")
    b.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    b.add_argument("--design-set", action="store_true")
    b.add_argument("--decider-url", default=DEFAULT_URL)
    b.add_argument("--decider-report", help="reuse an earlier Decider report.json instead of calling Decider again")
    b.add_argument("--model", default=DEFAULT_MODEL, help="Bedrock model or inference profile for the LLM side")
    b.add_argument("--region", default=DEFAULT_REGION)
    b.add_argument("--price-in", type=float, default=0.00006, help="USD per 1,000 input tokens (default: Nova Lite)")
    b.add_argument("--price-out", type=float, default=0.00024, help="USD per 1,000 output tokens (default: Nova Lite)")
    b.add_argument("--send-to-bedrock", action="store_true",
                   help="confirm that section text may go to Bedrock unredacted (synthetic or public documents only)")
    b.add_argument("--skip-llm", action="store_true")
    b.set_defaults(func=cmd_bench)

    sv = sub.add_parser("serve", help="start the review UI and its API (local only)")
    sv.add_argument("--pack-dir", default="rule-packs", help="built-in packs offered as templates")
    sv.add_argument("--workspace", default="out/ui", help="where uploads, reports and reviews are kept")
    sv.add_argument("--ui-dist", default="ui/dist")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    sv.add_argument("--decider-url", default=DEFAULT_URL)
    sv.add_argument("--bedrock", action="store_true", help="offer Bedrock-drafted fixes in the upload form")
    sv.add_argument("--model", default=DEFAULT_MODEL)
    sv.add_argument("--region", default=DEFAULT_REGION)
    sv.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
