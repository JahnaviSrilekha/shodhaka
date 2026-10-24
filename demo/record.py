"""Record the read-only API responses of a running `shodhaka serve` for the hosted replay demo.

    python demo/record.py --org <org id>          # writes demo/recorded-api/
    demo/build.sh                                 # builds the UI in demo mode around them

Only GET responses are stored, as JSON files named after their URL path, so a static host can serve them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "recorded-api"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000/api")
    parser.add_argument("--org", required=True, help="organization to record (and only that one)")
    args = parser.parse_args()
    shutil.rmtree(OUT, ignore_errors=True)

    def get(path: str, raw: bool = False):
        try:
            with urllib.request.urlopen(args.base + path, timeout=30) as r:
                body = r.read()
        except urllib.error.HTTPError as exc:
            print(f"skip {path} ({exc.code})")
            return None
        target = OUT / urllib.parse.unquote(path.lstrip("/"))
        target = target if raw else target.with_name(target.name + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return None if raw else json.loads(body)

    health = get("/health")
    get("/templates")
    orgs = [o for o in get("/orgs") if o["id"] == args.org]
    (OUT / "orgs.json").write_text(json.dumps(orgs))  # only the demo organization
    org = get(f"/orgs/{args.org}")
    for pack in org.get("general_packs", []):
        get(f"/orgs/{args.org}/packs/{pack['id']}")
    for project in org["projects"]:
        base = f"/orgs/{args.org}/projects/{project['id']}"
        detail = get(base)
        get(f"{base}/candidates")
        for pack in detail.get("project_packs", []):
            get(f"{base}/packs/{pack['id']}")
        for item in get(f"{base}/analyses"):
            analysis = get(f"{base}/analyses/{item['id']}")
            for doc in analysis["documents"]:
                quoted = "/".join(urllib.parse.quote(p) for p in doc.split("/"))
                get(f"{base}/analyses/{item['id']}/documents/{quoted}")
                get(f"{base}/analyses/{item['id']}/export/document/{quoted}", raw=True)
            for name in ("report.json", "expected.json", "rules.yaml"):
                get(f"{base}/analyses/{item['id']}/export/{name}", raw=True)
    files = [p for p in OUT.rglob("*") if p.is_file()]
    print(f"{len(files)} files in {OUT.relative_to(ROOT)} · Decider {health.get('checkpoint')}")


if __name__ == "__main__":
    main()
