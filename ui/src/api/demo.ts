// Recorded demo (built with VITE_DEMO=1): GET requests are answered from JSON files recorded from a
// real run (demo/record.py), so the UI can be hosted without Decider or a server.
// Review decisions are kept in memory for the visit; everything else that would change data is refused.
import type { Analysis, Finding, Review, ReviewInput } from "./types";

export const DEMO = import.meta.env.VITE_DEMO === "1";
export const DEMO_API = "demo-api";
export const DEMO_MESSAGE = "This is a recorded demo, so nothing can be changed or uploaded here. "
  + "Run Shodhaka locally with Strands Decider 2B to check your own documents.";

const findings = new Map<string, Finding>(); // "<analysis>/<finding>" -> finding
const decisions = new Map<string, Record<string, Review | null>>(); // analysis -> finding -> review (null = undone)

export class DemoRefused extends Error {}

export async function demoRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const review = path.match(/\/analyses\/([0-9a-f]+)\/reviews\/(.+)$/);
  if (review) {
    const [, analysisId, encoded] = review;
    const findingId = decodeURIComponent(encoded);
    const mine = decisions.get(analysisId) ?? {};
    decisions.set(analysisId, mine);
    if (method === "DELETE") {
      mine[findingId] = null;
      return undefined as T;
    }
    const input = JSON.parse(String(init?.body ?? "{}")) as ReviewInput;
    const finding = findings.get(`${analysisId}/${findingId}`);
    const saved: Review = {
      finding_id: findingId, rule_id: finding?.rule_id ?? "", document: finding?.document ?? "",
      decision: input.decision, verdict: input.verdict ?? "gap", tool_status: finding?.status ?? "gap",
      note: input.note ?? "", fix: input.fix ?? null, reviewed_at: new Date().toISOString(),
    };
    mine[findingId] = saved;
    return saved as T;
  }
  if (method !== "GET") throw new DemoRefused(DEMO_MESSAGE);

  const response = await fetch(`${DEMO_API}${path}.json`);
  if (!response.ok) throw new DemoRefused("This page is not part of the recorded demo.");
  const data = await response.json();
  const analysis = path.match(/\/analyses\/([0-9a-f]+)$/);
  if (analysis) {
    const a = data as Analysis;
    a.report?.findings.forEach((f) => findings.set(`${a.id}/${f.id}`, f));
    const reviews = { ...a.reviews };
    for (const [id, r] of Object.entries(decisions.get(a.id) ?? {})) {
      if (r) reviews[id] = r;
      else delete reviews[id];
    }
    a.reviews = reviews;
  }
  return data as T;
}
