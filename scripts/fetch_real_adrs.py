"""Download real ADRs listed in the Buchgeher et al. dataset, only from permissively licensed repos.

The dataset (CC BY 4.0) lists ADR file paths but does not contain the ADR texts; each ADR stays
under its own repository's licence. This script fetches them at run time into a folder that is
git-ignored, and writes ATTRIBUTION.md with the source and licence of every file.

    python scripts/fetch_real_adrs.py \
        --csv ~/Downloads/replication_package_ADR/replication_package/Data_collection/adr_template.csv \
        --out data/real-adrs --max-repos 15 --keywords

Set GITHUB_TOKEN to raise GitHub's API limit (60 requests/hour without a token).
Dataset: G. Buchgeher et al., "Using Architecture Decision Records in Open Source Projects -
An MSR Study on GitHub", IEEE Access 2023, DOI 10.1109/ACCESS.2023.3287654 (CC BY 4.0).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

PERMISSIVE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "cc-by-4.0", "cc0-1.0", "unlicense", "0bsd"}
KEYWORDS = re.compile(
    r"(database|\bdb\b|schema|event|messag|queue|kafka|rabbit|outbox|api|service|timeout|retry|"
    r"circuit|trac|correlat|secret|vault|docker|container|config|logging)", re.I)


def get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept, "User-Agent": "shodhaka"}
    if os.environ.get("GITHUB_TOKEN") and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return response.read()


def repo_info(owner: str, repo: str) -> dict | None:
    try:
        return json.loads(get(f"https://api.github.com/repos/{owner}/{repo}"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            sys.exit("GitHub API refused the request (403): usually the hourly limit. Set GITHUB_TOKEN or try again later.")
        return None  # deleted, renamed or private by now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, help="adr_template.csv or adr_all.csv from the dataset")
    parser.add_argument("--out", default="data/real-adrs")
    parser.add_argument("--max-repos", type=int, default=15)
    parser.add_argument("--max-per-repo", type=int, default=10)
    parser.add_argument("--keywords", action="store_true",
                        help="only ADRs whose file name mentions databases, events, APIs, secrets, containers ...")
    parser.add_argument("--repo", action="append", default=[], metavar="OWNER/REPO",
                        help="only these repositories (repeatable), e.g. --repo apache/james-project")
    parser.add_argument("--accepted-only", action="store_true", help="skip ADRs not marked Accepted")
    args = parser.parse_args()

    by_repo: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in csv.DictReader(open(Path(args.csv).expanduser(), encoding="utf-8")):
        if args.repo and f"{row['OWNER']}/{row['REPO']}".lower() not in {r.lower() for r in args.repo}:
            continue
        if args.keywords and not KEYWORDS.search(row["ADR_file"]):
            continue
        if args.accepted_only and not row.get("Status", "").lower().startswith("accepted"):
            continue
        by_repo[(row["OWNER"], row["REPO"])].append(row["ADR_file"])

    ranked = sorted(by_repo.items(), key=lambda kv: -len(kv[1]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    attribution = ["# Sources of the real ADRs in this folder", "",
                   "Selected with the dataset of Buchgeher et al., IEEE Access 2023, "
                   "DOI 10.1109/ACCESS.2023.3287654 (dataset licence CC BY 4.0).",
                   "Each ADR remains under the licence of its own repository, listed below.", "",
                   "| Repository | Licence | Files |", "|---|---|---|"]
    used = skipped_licence = 0
    for (owner, repo), paths in ranked:
        if used >= args.max_repos:
            break
        info = repo_info(owner, repo)
        if not info:
            print(f"skip {owner}/{repo}: not reachable")
            continue
        licence = ((info.get("license") or {}).get("spdx_id") or "none").lower()
        if licence not in PERMISSIVE:
            skipped_licence += 1
            print(f"skip {owner}/{repo}: licence {licence}")
            continue
        branch = info.get("default_branch", "HEAD")
        target = out / f"{owner}--{repo}"
        target.mkdir(exist_ok=True)
        saved = 0
        for path in paths[: args.max_per_repo]:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
            try:
                (target / Path(path).name).write_bytes(get(url, accept="text/plain"))
                saved += 1
            except urllib.error.HTTPError:
                print(f"  missing now: {path}")
        if saved:
            used += 1
            attribution.append(f"| [{owner}/{repo}](https://github.com/{owner}/{repo}) | {licence.upper()} | {saved} |")
            print(f"ok   {owner}/{repo} ({licence}): {saved} ADRs")
        else:
            target.rmdir()
    (out / "ATTRIBUTION.md").write_text("\n".join(attribution) + "\n", encoding="utf-8")
    print(f"\n{used} repos saved to {out}; {skipped_licence} skipped for licence. See {out / 'ATTRIBUTION.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
