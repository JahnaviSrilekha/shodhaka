"""Download the architecture docs, configs and Dockerfiles of a few open-source microservice
projects, pinned to one commit each, so the rule pack can be tried on real designs.

    python scripts/fetch_project_docs.py                       # all projects below, into data/projects
    python scripts/fetch_project_docs.py --only piggymetrics   # one project
    gapanalyzer run --pack rule-packs/acme-arch.yaml --docs data/projects/piggymetrics --out out/projects/piggymetrics

Only permissively licensed repositories are used (checked through the GitHub API at download
time). The files stay under data/ (git-ignored) and are not redistributed with this repo;
data/projects/ATTRIBUTION.md records source, licence and commit for each one.
File names are flattened (`account-service__bootstrap.yml`) so they stay unique when uploaded in the UI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ALLOWED_LICENCES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"}

# name -> (repo, files to keep (regex on the repo path), why it is a useful test)
PROJECTS = {
    "piggymetrics": (
        "sqshq/piggymetrics",
        r"^README\.md$|^[^/]+/src/main/resources/(bootstrap|application)[^/]*\.ya?ml$|^config/src/main/resources/shared/[^/]+\.ya?ml$|^[^/]+/Dockerfile$",
        "Java/Spring Cloud: database per service, Hystrix timeouts and fallbacks, config server, Dockerfiles",
    ),
    "spring-petclinic-microservices": (
        "spring-petclinic/spring-petclinic-microservices",
        r"^README\.md$|^[^/]+/src/main/resources/application[^/]*\.ya?ml$|^docker/Dockerfile$",
        "Java/Spring Cloud: gateway, discovery, config server, tracing, per-service configs",
    ),
    "modular-monolith-with-ddd": (
        "kgrzybek/modular-monolith-with-ddd",
        r"^docs/architecture-decision-log/\d{4}-[^/]+\.md$",
        "17 real ADRs: module boundaries, event-driven communication, outbox-style integration events",
    ),
    "opentelemetry-demo": (
        "open-telemetry/opentelemetry-demo",
        r"^README\.md$|^src/(ad|cart|checkout|payment|shipping|quote|currency|email|product-catalog|recommendation|accounting|fraud-detection)/(README\.md|Dockerfile)$",
        "Polyglot microservices built around tracing: tests the correlation-ID rule and base images",
    ),
}
NOISE = {"src", "main", "resources", "docs"}


def api(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "shodhaka"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:  # only ever sent to api.github.com
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def raw(repo: str, sha: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "shodhaka"}), timeout=30) as r:
        return r.read()


def flat_name(path: str) -> str:
    parts = [p for p in path.split("/") if p not in NOISE]
    if parts[-1] == "Dockerfile" and len(parts) > 1:  # keep a name the analyzer recognises: <service>.Dockerfile
        return "__".join(parts[:-1]) + ".Dockerfile"
    return "__".join(parts) if len(parts) > 1 else parts[0]


def fetch(name: str, out: Path) -> dict:
    repo, pattern, why = PROJECTS[name]
    meta = api(f"https://api.github.com/repos/{repo}")
    licence = (meta.get("license") or {}).get("spdx_id")
    if licence not in ALLOWED_LICENCES:
        print(f"skip {repo}: licence {licence} is not on the allow list", file=sys.stderr)
        return {}
    branch = meta["default_branch"]
    sha = api(f"https://api.github.com/repos/{repo}/commits/{branch}")["sha"]
    tree = api(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1")
    paths = sorted(t["path"] for t in tree["tree"] if t["type"] == "blob" and re.search(pattern, t["path"]))
    target = out / name
    target.mkdir(parents=True, exist_ok=True)
    files = []
    for path in paths:
        data = raw(repo, sha, path)
        (target / flat_name(path)).write_bytes(data)
        files.append((flat_name(path), path, len(data)))
    print(f"{name}: {len(files)} files from {repo}@{sha[:10]} ({licence})")
    return {"name": name, "repo": repo, "licence": licence, "sha": sha, "why": why, "files": files}


def write_attribution(out: Path, records: list[dict]) -> None:
    lines = ["# Sources", "",
             "Downloaded by scripts/fetch_project_docs.py for local evaluation only; not redistributed.",
             "Each file keeps the licence of its repository.", ""]
    for r in records:
        lines += [f"## {r['name']}", "",
                  f"- Repository: https://github.com/{r['repo']} (licence {r['licence']})",
                  f"- Commit: {r['sha']}", f"- Why it is here: {r['why']}", "",
                  "| File here | Path in the repository | Bytes |", "|---|---|---|"]
        lines += [f"| {f} | [{p}](https://github.com/{r['repo']}/blob/{r['sha']}/{p}) | {n} |" for f, p, n in r["files"]]
        lines.append("")
    (out / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/projects")
    parser.add_argument("--only", action="append", choices=sorted(PROJECTS), help="fetch just this project (repeatable)")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records = [r for r in (fetch(n, out) for n in (args.only or PROJECTS)) if r]
    previous = out / "ATTRIBUTION.md"
    if args.only and previous.exists():
        print("note: ATTRIBUTION.md now lists only the projects fetched in this run", file=sys.stderr)
    write_attribution(out, records)
    print(f"done: {sum(len(r['files']) for r in records)} files under {out}; sources in {out / 'ATTRIBUTION.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
