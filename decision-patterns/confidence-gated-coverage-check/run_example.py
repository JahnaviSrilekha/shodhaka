"""Run the pattern on example.json against a local Decider.

    strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099
    python run_example.py
"""

import json
import sys
from pathlib import Path

from coverage_check import Rule, check, decider_http

example = json.loads(Path(__file__).with_name("example.json").read_text())
rules = [Rule(**r) for r in example["rules"]]
threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.75

print(f"{'rule':8} {'status':15} {'conf':>5}  section            expected")
for v in check(example["sections"], rules, decider_http(), threshold):
    print(f"{v.rule:8} {v.status:15} {v.confidence:5.2f}  {str(v.section):18} {example['expected'][v.rule]}")
