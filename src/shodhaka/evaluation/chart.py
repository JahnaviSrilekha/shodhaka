"""Accuracy and gap-detection scores as a grouped bar chart, written as a standalone SVG.

No plotting library: the SVG renders on GitHub, in the browser and in the article, and follows
the viewer's light or dark mode. One panel per evaluation set, one bar per system and metric.
"""

from __future__ import annotations

from html import escape
from typing import Any

METRICS = [("exact_accuracy", "Accuracy"), ("gap_precision", "Gap precision"),
           ("gap_recall_strict", "Gap recall"), ("gap_f1", "Gap F1")]
AGENT_METRICS = [("task_completion", "Task completion"), ("tool_effectiveness", "Tool effectiveness"),
                 ("step_efficiency", "Step efficiency"), ("reasoning_quality", "Reasoning quality")]

# Categorical slots 1 and 2 (blue, orange), stepped separately for light and dark surfaces.
STYLE = """
  .surface { fill: #fcfcfb } .title { fill: #0b0b0b; font: 600 15px system-ui, sans-serif }
  .label { fill: #52514e; font: 12px system-ui, sans-serif } .value { fill: #0b0b0b; font: 11px system-ui, sans-serif }
  .grid { stroke: #e4e3df; stroke-width: 1 } .axis { stroke: #a8a7a1; stroke-width: 1 }
  .s0 { fill: #2a78d6 } .s1 { fill: #eb6834 }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19 } .title, .value { fill: #f0efec } .label { fill: #c3c2b7 }
    .grid { stroke: #33322f } .axis { stroke: #6b6a65 } .s0 { fill: #3987e5 } .s1 { fill: #d95926 }
  }
"""


def _pct(value: float) -> str:
    return f"{value * 100:.1f}".removesuffix(".0")


def _bar(x: float, y: float, w: float, h: float, cls: str, tip: str) -> str:
    """A bar with 4px rounded top corners, square at the baseline."""
    r = min(4.0, w / 2, h)
    path = (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")
    return f'<path class="{cls}" d="{path}"><title>{escape(tip)}</title></path>'


def svg(panels: list[tuple[str, list[dict[str, Any]]]], title: str = "Decider 2B vs LLM: accuracy and F1",
        metrics: list[tuple[str, str]] = METRICS, out_of: int = 100) -> str:
    """`panels` is [(set name, [result row per system])]; rows come from bench.summarise().
    Values are fractions (0-1). `out_of` sets the scale shown: 100 for percentages, 5 for a 1-5 rubric."""
    systems = [row["system"] for row in panels[0][1]]
    bar_w, gap, group_gap = 30, 2, 22
    group_w = len(systems) * bar_w + (len(systems) - 1) * gap
    plot_h, top, left = 190, 104, 44
    panel_w = max(380, 18 + len(metrics) * (group_w + group_gap) + 24)
    width, height = left + panel_w * len(panels) + 16, top + plot_h + 64
    show = (lambda v: _pct(v)) if out_of == 100 else (lambda v: f"{v * out_of:.1f}")
    ticks = [(f / 4, f"{f * 25}%") for f in range(5)] if out_of == 100 else [(i / out_of, str(i)) for i in range(out_of + 1)]

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'role="img" aria-label="{escape(title)}"><style>{STYLE}</style>',
           f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
           f'<text class="title" x="{left}" y="26">{escape(title)}</text>']
    x = left
    for i, name in enumerate(systems):  # legend
        out.append(f'<rect class="s{i}" x="{x}" y="38" width="12" height="12" rx="3"/>'
                   f'<text class="label" x="{x + 18}" y="48">{escape(name)}</text>')
        x += 24 + 7 * len(name)

    for p, (set_name, rows) in enumerate(panels):
        x0 = left + p * panel_w
        base = top + plot_h
        for frac, tick_label in ticks:
            y = base - plot_h * frac
            out.append(f'<line class="{"axis" if frac == 0 else "grid"}" x1="{x0}" x2="{x0 + panel_w - 24}" y1="{y:.1f}" y2="{y:.1f}"/>')
            if p == 0:
                out.append(f'<text class="label" x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end">{tick_label}</text>')
        out.append(f'<text class="label" x="{x0}" y="{top - 26}">{escape(set_name)}</text>')
        gx = x0 + 18
        for key, label in metrics:
            for s, row in enumerate(rows):
                value = row.get(key)
                if value is None:
                    continue
                h = plot_h * value
                bx = gx + s * (bar_w + gap)
                out.append(_bar(bx, base - h, bar_w, h, f"s{s}", f"{row['system']}, {label}: {show(value)}"))
                out.append(f'<text class="value" x="{bx + bar_w / 2:.1f}" y="{base - h - 5:.1f}" '
                           f'text-anchor="middle">{show(value)}</text>')
            cx = gx + group_w / 2
            lines = "".join(f'<tspan x="{cx:.1f}" dy="{0 if i == 0 else 14}">{escape(word)}</tspan>'
                            for i, word in enumerate(label.split(" ", 1)))
            out.append(f'<text class="label" y="{base + 18}" text-anchor="middle">{lines}</text>')
            gx += group_w + group_gap
    out.append("</svg>")
    return "\n".join(out)
