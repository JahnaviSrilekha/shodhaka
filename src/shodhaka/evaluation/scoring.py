"""Score a report against planted ground truth (expected.json).

Strict: only `gap` counts as catching a gap. Lenient: `needs_review` also counts, because a
human sees it. The "false alarm" rate is gaps reported where the truth is compliant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def evaluate(report: dict[str, Any], expected_path: str | Path) -> dict[str, Any]:
    expected = json.loads(Path(expected_path).read_text(encoding="utf-8"))["expected"]
    by_key = {(f["rule_id"], f["document"]): f for f in report["findings"]}
    rows, missing = [], []
    for item in expected:
        finding = by_key.get((item["rule"], item["file"]))
        if finding is None:
            missing.append(item)
            continue
        rows.append({"rule": item["rule"], "file": item["file"], "expected": item["verdict"],
                     "status": finding["status"], "decided_by": finding["decided_by"],
                     "confidence": finding["confidence"]})

    gaps = [r for r in rows if r["expected"] == "gap"]
    compliant = [r for r in rows if r["expected"] == "compliant"]
    caught_strict = sum(r["status"] == "gap" for r in gaps)
    caught_lenient = sum(r["status"] in ("gap", "needs_review") for r in gaps)
    false_alarms = sum(r["status"] == "gap" for r in compliant)
    correct = sum(
        (r["expected"] == "gap" and r["status"] == "gap")
        or (r["expected"] == "compliant" and r["status"] == "covered")
        or (r["expected"] == "not_applicable" and r["status"] == "not_applicable")
        for r in rows
    )
    escalated = sum(r["status"] == "needs_review" for r in rows)

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    return {
        "items": len(expected),
        "missing_findings": missing,
        "gap_recall_strict": ratio(caught_strict, len(gaps)),
        "gap_recall_with_review": ratio(caught_lenient, len(gaps)),
        "false_alarm_rate": ratio(false_alarms, len(compliant)),
        "exact_accuracy": ratio(correct, len(rows)),
        "escalation_rate": ratio(escalated, len(rows)),
        "rows": rows,
    }


def rescore(report: dict[str, Any], threshold: float) -> dict[str, Any]:
    """Re-apply the confidence gate at another threshold, from the per-section answers already
    stored in the report. No model calls: tuning the threshold costs nothing."""
    from shodhaka.analysis.engine import gate

    findings = []
    for f in report["findings"]:
        f = dict(f)
        if f["decided_by"] == "decider":
            f["status"], f["confidence"], f["reason"] = gate(f["sections"], threshold, f.get("scope", "section"))
        findings.append(f)
    return {**report, "threshold": threshold, "findings": findings}


def calibrate(report: dict[str, Any], expected_path: str | Path,
              thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)) -> list[dict[str, Any]]:
    rows = []
    for t in thresholds:
        result = evaluate(rescore(report, t), expected_path)
        rows.append({"threshold": t, **{k: result[k] for k in (
            "gap_recall_strict", "gap_recall_with_review", "false_alarm_rate", "exact_accuracy", "escalation_rate")}})
    return rows


def compare(full: dict[str, Any], shortlisted: dict[str, Any]) -> dict[str, Any]:
    """What retrieval saved and what it cost, against a run that checked every section.

    A section-rule pair counts as relevant when the full run's stage 1 found it on topic
    (verdict compliant or gap). Retrieval recall = share of those pairs retrieval still checked."""
    def pairs(report):
        out = {}
        for f in report["findings"]:
            for s in f.get("sections", []):
                out[(f["rule_id"], f["document"], s["section"])] = s
        return out

    a, b = pairs(full), pairs(shortlisted)
    relevant = [k for k, s in a.items() if s["verdict"] in ("compliant", "gap")]
    kept = [k for k in relevant if k in b and b[k]["option"] != "not-checked-retrieval"]
    status_a = {(f["rule_id"], f["document"]): f["status"] for f in full["findings"]}
    changed = []
    for f in shortlisted["findings"]:
        before = status_a.get((f["rule_id"], f["document"]))
        if before != f["status"]:
            changed.append({"rule": f["rule_id"], "document": f["document"], "full": before, "retrieval": f["status"]})
    return {
        "retrieval": shortlisted.get("retrieval", {}),
        "decider_calls": {"full": full["decider"].get("calls"), "retrieval": shortlisted["decider"].get("calls")},
        "relevant_pairs": len(relevant),
        "relevant_pairs_kept": len(kept),
        "retrieval_recall": round(len(kept) / len(relevant), 3) if relevant else None,
        "missed_pairs": [{"rule": k[0], "document": k[1], "section": k[2]} for k in relevant if k not in kept],
        "findings_changed": changed,
    }
