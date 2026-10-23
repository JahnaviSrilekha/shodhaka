"""Draw accuracy / F1 and the four agent metrics for several benchmark runs side by side.

    python scripts/plot_results.py out/bench/visible out/bench/heldout --out docs/results/accuracy-f1.svg

Writes the accuracy chart to --out and the agent metrics chart next to it (agent-metrics.svg).

Each folder is the --out of a `shodhaka bench` run. The scores are recomputed from the saved
reports (decider/report.json and llm/report.json) against the run's expected.json, so older runs
get precision, F1 and the agent metrics too. No model calls.
"""

import argparse
import json
from pathlib import Path

from shodhaka.evaluation import chart
from shodhaka.evaluation.agent_metrics import agent_metrics
from shodhaka.evaluation.scoring import evaluate

NAMES = {"decider": "Strands Decider 2B (local)", "llm": "Nova Lite (Bedrock)"}
SETS = {"visible": "Tuning set", "heldout": "Held-out set"}


def panel(run: Path) -> tuple[str, list[dict]]:
    meta = json.loads((run / "bench.json").read_text(encoding="utf-8"))
    expected = Path(meta["expected"])
    rows = []
    for key, name in NAMES.items():
        report = run / key / "report.json"
        if report.exists():
            data = json.loads(report.read_text(encoding="utf-8"))
            scores = evaluate(data, expected)
            rows.append({"system": name, **scores, **agent_metrics(data, scores)})
    folder = Path(meta["docs"]).name
    label = f"{SETS.get(folder, folder)}: {rows[0]['items']} checks, gate {meta['threshold']}"
    return label, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("docs/results/accuracy-f1.svg"))
    args = parser.parse_args()
    panels = [panel(run) for run in args.runs]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(chart.svg(panels, "Decider 2B vs Nova Lite: accuracy and F1"), encoding="utf-8")
    agent_out = args.out.with_name("agent-metrics.svg")
    agent_out.write_text(chart.svg(panels, "Decider 2B vs Nova Lite: agent metrics", chart.AGENT_METRICS), encoding="utf-8")
    for label, rows in panels:
        print(label)
        for r in rows:
            print(f"  {r['system']:28} accuracy {r['exact_accuracy']:.3f}  precision {r['gap_precision']:.3f}  "
                  f"recall {r['gap_recall_strict']:.3f}  F1 {r['gap_f1']:.3f}")
            print(f"  {'':28} completion {r['task_completion']:.3f}  tools {r['tool_effectiveness']:.3f}  "
                  f"steps saved {r['step_efficiency']:.3f}  reasoning {r['reasoning_quality']:.3f}")
    print(f"written: {args.out} and {agent_out}")


if __name__ == "__main__":
    main()
