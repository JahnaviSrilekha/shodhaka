"""Four agent-level metrics, computed from a report and its scores (no model calls).

A *task* is one labelled rule check on one document. The definitions are deliberately plain so
anyone can recompute them from report.json:

task_completion      checks that ended in a final verdict (gap, covered, not applicable) without
                     being handed to a person / all checks (an unusable model reply ends in review)
tool_effectiveness   model requests that returned something usable / all model requests. Unusable:
                     a reply that does not parse, or a reported gap whose evidence question
                     brought back no quotable sentence
step_efficiency      model requests saved against the naive plan of one request per rule and
                     section: 1 - requests / (rule, section) pairs
reasoning_quality    of the verdicts the model committed to (decided by the model, not escalated),
                     the share that were right
"""

from __future__ import annotations

from typing import Any

RIGHT = {("gap", "gap"), ("compliant", "covered"), ("not_applicable", "not_applicable")}


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def agent_metrics(report: dict[str, Any], scores: dict[str, Any]) -> dict[str, Any]:
    rows = scores["rows"]
    stats = report.get("decider", {})
    calls, failures = stats.get("calls") or 0, stats.get("failures") or 0
    pairs = (report.get("retrieval") or {}).get("pairs_total") or 0

    final = [r for r in rows if r["status"] != "needs_review"]  # a reply that failed to parse lands in review

    gaps = [f for f in report["findings"] if f["status"] == "gap" and f["decided_by"] == "decider"]
    usable = calls - failures - sum(not f.get("evidence") for f in gaps)

    committed = [r for r in final if r["decided_by"] == "decider"]
    right = sum((r["expected"], r["status"]) in RIGHT for r in committed)

    return {
        "task_completion": _ratio(len(final), len(rows)),
        "tool_effectiveness": _ratio(max(usable, 0), calls),
        "step_efficiency": round(1 - calls / pairs, 3) if pairs and calls else None,
        "reasoning_quality": _ratio(right, len(committed)),
    }
