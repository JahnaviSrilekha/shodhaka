import csv
from pathlib import Path

from gapanalyzer.engine import analyze
from gapanalyzer.evaluate import evaluate
from gapanalyzer.review import read_sheet, score, to_expected, write_sheet


def _label(path: Path, verdicts: dict[tuple[str, str], str]) -> None:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        r["your_verdict"] = verdicts.get((r["rule_id"], r["document"]), "")
    with open(path, "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows)


def test_sheet_round_trip_gives_precision_and_eval_ground_truth(pack, visible_docs, scripted, tmp_path):
    report = analyze(pack, visible_docs, scripted)
    sheet = tmp_path / "review.csv"
    n = write_sheet(report, sheet)
    assert n == sum(f["status"] != "not_applicable" for f in report["findings"])
    first = list(csv.DictReader(open(sheet, encoding="utf-8")))[0]
    assert first["tool_status"] == "gap" and first["your_verdict"] == ""

    gaps = [(f["rule_id"], f["document"]) for f in report["findings"] if f["status"] == "gap"]
    labels = {k: "gap" for k in gaps}
    labels[gaps[0]] = "compliant"            # the reviewer disagrees with one flagged gap
    _label(sheet, labels)
    filled, problems = read_sheet(sheet)
    assert not problems
    s = score(filled)
    assert s["flagged_gaps_labelled"] == len(gaps)
    assert s["precision_of_flagged_gaps"] == round((len(gaps) - 1) / len(gaps), 3)
    assert len(s["false_alarms"]) == 1

    expected = tmp_path / "expected.json"
    import json
    expected.write_text(json.dumps(to_expected(filled, pack.pack)))
    assert evaluate(report, expected)["false_alarm_rate"] == 1.0  # the one 'compliant' label was flagged


def test_bad_verdicts_are_reported_not_guessed(tmp_path):
    sheet = tmp_path / "s.csv"
    sheet.write_text("rule_id,document,tool_status,your_verdict\nARCH-01,a.md,gap,maybe\nARCH-02,a.md,gap,Not Applicable\n")
    filled, problems = read_sheet(sheet)
    assert len(problems) == 1 and "maybe" in problems[0]
    assert filled[0]["your_verdict"] == "not_applicable"


def test_all_includes_not_applicable_rows_for_recall(pack, visible_docs, scripted, tmp_path):
    report = analyze(pack, visible_docs, scripted)
    assert write_sheet(report, tmp_path / "a.csv", include_not_applicable=True) == len(report["findings"])
