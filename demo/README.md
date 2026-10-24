# Hosted replay demo

A read-only copy of the Shodhaka UI that runs without Strands Decider or a server, for judges and
anyone without a local setup: **https://jahnavisrilekha.github.io/shodhaka/**

Every finding, confidence, evidence sentence, removal and cost on it comes from a real local run
(Strands Decider 2B on Apple silicon, fixes by Nova Lite on Bedrock, 24 October 2026). You can browse,
filter and approve; uploading, editing and re-checking need the real app (see the main README).

| File | What it is |
|---|---|
| `record.py` | Saves the GET responses of a running `shodhaka serve` for one organization |
| `recorded-api/` | Those responses, as JSON files named after their URL path |
| `build.sh` | Builds the UI with `VITE_DEMO=1` around them into `out/demo-site` |

The only demo code inside the app is `ui/src/api/demo.ts`, which answers requests from the recordings
when the UI is built in demo mode. A normal build ignores it.

```bash
shodhaka serve --bedrock                        # with the analyses you want to show
python demo/record.py --org <organization id>
demo/build.sh                                   # then publish out/demo-site (GitHub Pages: gh-pages branch)
```
