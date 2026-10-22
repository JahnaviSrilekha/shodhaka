"""Human review of a report: the way to measure real-world documents that have no ground truth.

    gapanalyzer review-sheet out/real/report.json --out review.csv          # gaps, reviews, covered
    gapanalyzer review-sheet out/real/report.json --out review.csv --all    # also "not applicable" rows
    # open review.csv in Numbers or Excel, fill `your_verdict` with gap / compliant / not_applicable
    gapanalyzer review-score review.csv --expected-out data/real-expected.json
    gapanalyzer eval out/real/report.json data/real-expected.json -v

Precision needs only the rows the tool flagged as gaps. Recall needs every row of the documents you
label (use --all), otherwise a gap the tool called "not applicable" can never be counted as missed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

VERDICTS = {"gap", "compliant", "not_applicable"}
ORDER = {"gap": 0, "needs_review": 1, "covered": 2, "not_applicable": 3}
COLUMNS = ["rule_id", "rule_title", "document", "tool_status", "confidence", "decided_by",
           "evidence_section", "evidence_text", "reason", "your_verdict", "notes"]


def write_sheet(report: dict[str, Any], path: Path, include_not_applicable: bool = False) -> int:
    rows = [f for f in report["findings"] if include_not_applicable or f["status"] != "not_applicable"]
    rows.sort(key=lambda f: (ORDER[f["status"]], f["document"], f["rule_id"]))
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for f in rows:
            evidence = (f.get("evidence") or [{}])[0]
            writer.writerow({
                "rule_id": f["rule_id"], "rule_title": f["rule_title"], "document": f["document"],
                "tool_status": f["status"], "confidence": f"{f['confidence']:.2f}", "decided_by": f["decided_by"],
                "evidence_section": evidence.get("section") or (f"line {evidence['line']}" if evidence.get("line") else ""),
                "evidence_text": " ".join(str(evidence.get("text", "")).split())[:400],
                "reason": f.get("reason", ""), "your_verdict": "", "notes": "",
            })
    return len(rows)


def read_sheet(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Filled rows and a list of problems (unknown verdict values)."""
    filled, problems = [], []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=2):
            verdict = (row.get("your_verdict") or "").strip().lower().replace(" ", "_").replace("n/a", "not_applicable")
            if not verdict:
                continue
            if verdict not in VERDICTS:
                problems.append(f"row {number}: your_verdict '{row['your_verdict']}' is not one of gap, compliant, not_applicable")
                continue
            filled.append({**row, "your_verdict": verdict})
    return filled, problems


def score(filled: list[dict[str, str]]) -> dict[str, Any]:
    flagged = [r for r in filled if r["tool_status"] == "gap"]
    true_gaps = [r for r in flagged if r["your_verdict"] == "gap"]
    reviews = [r for r in filled if r["tool_status"] == "needs_review"]
    covered = [r for r in filled if r["tool_status"] == "covered"]
    missed = [r for r in filled if r["your_verdict"] == "gap" and r["tool_status"] in ("covered", "not_applicable")]

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    return {
        "labelled_rows": len(filled),
        "flagged_gaps_labelled": len(flagged),
        "precision_of_flagged_gaps": ratio(len(true_gaps), len(flagged)),
        "false_alarms": [f"{r['rule_id']} {r['document']}" for r in flagged if r["your_verdict"] != "gap"],
        "needs_review_that_were_gaps": ratio(sum(r["your_verdict"] == "gap" for r in reviews), len(reviews)),
        "covered_confirmed": ratio(sum(r["your_verdict"] == "compliant" for r in covered), len(covered)),
        "missed_gaps_in_labelled_rows": [f"{r['rule_id']} {r['document']} (tool: {r['tool_status']})" for r in missed],
    }


def to_expected(filled: list[dict[str, str]], pack: str) -> dict[str, Any]:
    return {
        "pack": pack,
        "note": "Human-labelled from a review sheet. Only labelled rows are scored.",
        "expected": [{"rule": r["rule_id"], "file": r["document"], "verdict": r["your_verdict"],
                      **({"note": r["notes"]} if r.get("notes") else {})} for r in filled],
    }
