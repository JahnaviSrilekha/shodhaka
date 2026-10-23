"""Write the gap report as JSON (the contract) and as a self-contained HTML page."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

STATUS_LABEL = {
    "gap": "Gap",
    "needs_review": "Needs review",
    "covered": "Covered (sign-off pending)",
    "not_applicable": "Not applicable",
}
ORDER = {"gap": 0, "needs_review": 1, "covered": 2, "not_applicable": 3}
SEVERITY = {"high": 0, "medium": 1, "low": 2}

CSS = """
:root{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--muted:#5f5e5a;--line:#e3e1db;--gap:#b42318;--review:#b54708;--ok:#067647;--na:#667085}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ededea;--muted:#a3a29c;--line:#34332f;--gap:#f97066;--review:#fdb022;--ok:#47cd89;--na:#98a2b3}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:24px}
.tile span{color:var(--muted);font-size:13px}.f{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 12px}
.f h3{margin:0;font-size:16px}.meta{color:var(--muted);font-size:13px;margin:2px 0 8px}.pill{display:inline-block;font-size:12px;font-weight:600;border-radius:99px;padding:2px 9px;border:1px solid currentColor;margin-right:6px}
.gap{color:var(--gap)}.needs_review{color:var(--review)}.covered{color:var(--ok)}.not_applicable{color:var(--na)}
blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid var(--line);color:var(--ink)}.fix{margin-top:8px}.fix b{font-size:13px}
details{margin-top:20px}code{font-size:13px}
"""


def write_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _finding_html(f: dict[str, Any]) -> str:
    e = html.escape
    evidence = "".join(
        f"<blockquote>{e(item.get('text', ''))}"
        f"<div class='meta'>{e(item.get('section', '') or ('line ' + str(item.get('line', ''))))}</div></blockquote>"
        for item in f.get("evidence", [])
    )
    confidence = "" if f["decided_by"] == "code" else f" · confidence {f['confidence']:.2f}"
    fix = (f"<div class='fix'><b>Suggested fix ({e(f.get('fix_source', ''))})</b><div>{e(f['suggested_fix'])}</div></div>"
           if f.get("suggested_fix") else "")
    return (
        f"<article class='f' data-testid='finding-{e(f['id'])}' data-status='{e(f['status'])}'>"
        f"<span class='pill {e(f['status'])}'>{e(STATUS_LABEL[f['status']])}</span>"
        f"<span class='pill'>{e(f['severity'])}</span>"
        f"<h3>{e(f['rule_id'])} · {e(f['rule_title'])}</h3>"
        f"<div class='meta'>{e(f['document'])} · decided by {e(f['decided_by'])}"
        f"{confidence} · {e(f.get('reason', ''))}</div>{evidence}{fix}"
        f"<div class='meta'>Human decision: {e(f['human_decision'])}</div></article>"
    )


def write_html(report: dict[str, Any], path: Path) -> None:
    e = html.escape
    findings = sorted(report["findings"], key=lambda f: (ORDER[f["status"]], SEVERITY[f["severity"]], f["rule_id"]))
    visible = [f for f in findings if f["status"] != "not_applicable"]
    hidden = [f for f in findings if f["status"] == "not_applicable"]
    s, dec, egress = report["summary"], report.get("decider", {}), report.get("egress", {})
    tiles = "".join(
        f"<div class='tile'><b class='{k}'>{s.get(k, 0)}</b><span>{STATUS_LABEL[k]}</span></div>"
        for k in ("gap", "needs_review", "covered")
    ) + (
        f"<div class='tile'><b>{dec.get('calls', 0)}</b><span>Decider calls · p50 {dec.get('latency_ms_p50') or '-'} ms</span></div>"
        f"<div class='tile'><b>{egress.get('bytes_sent', 0)}</b><span>bytes sent to Bedrock</span></div>"
    )
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Gap report · {e(report['pack']['id'])}</title><style>{CSS}</style></head><body><main>"
        f"<h1>Gap report: {e(report['pack']['title'])}</h1>"
        f"<p class='sub'>Pack {e(report['pack']['id'])} v{e(report['pack']['version'])} · "
        f"{len(report['documents'])} documents · confidence threshold {report['threshold']:.2f} · run {e(report['run_id'])}</p>"
        f"<div class='tiles'>{tiles}</div>"
        + "".join(_finding_html(f) for f in visible)
        + (f"<details><summary>{len(hidden)} not applicable</summary>" + "".join(_finding_html(f) for f in hidden) + "</details>" if hidden else "")
        + "</main></body></html>"
    )
    path.write_text(page, encoding="utf-8")
