#!/usr/bin/env bash
# Build the hosted replay: the real UI in demo mode around the responses recorded by demo/record.py.
#   demo/build.sh                    # -> out/demo-site, a static site (GitHub Pages, S3, any host)
set -euo pipefail
cd "$(dirname "$0")/.."
START="${DEMO_START:-/o/ec6f0c3115b9/p/d2b13441cde4/a/f5d963c54aa5}"
(cd ui && VITE_DEMO=1 VITE_DEMO_START="$START" npx vite build --base ./ --outDir ../out/demo-site --emptyOutDir)
cp -R demo/recorded-api out/demo-site/demo-api
touch out/demo-site/.nojekyll
echo "built out/demo-site ($(find out/demo-site -type f | wc -l | tr -d ' ') files)"
