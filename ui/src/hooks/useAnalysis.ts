import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Scope } from "../api/client";
import type { Analysis, Review, ReviewInput } from "../api/types";

const POLL_MS = 1000;

/**
 * Loads one analysis, polls while the Decider is working, and owns review mutations
 * (optimistic: the UI updates at once and rolls back if the server refuses).
 */
export function useAnalysis(scope: Scope, id: string) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    window.clearTimeout(timer.current);
    try {
      const next = await api.analysis(scope, id);
      setAnalysis(next);
      setError(null);
      if (next.status === "queued" || next.status === "cleaning" || next.status === "running") timer.current = window.setTimeout(load, POLL_MS);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [scope.org, scope.project, id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setAnalysis(null);
    load();
    return () => window.clearTimeout(timer.current);
  }, [load]);

  const review = useCallback(
    async (findingId: string, input: ReviewInput) => {
      const before = analysis?.reviews[findingId];
      const finding = analysis?.report?.findings.find((f) => f.id === findingId);
      if (!analysis || !finding) return;
      const optimistic: Review = {
        finding_id: findingId, rule_id: finding.rule_id, document: finding.document,
        decision: input.decision, verdict: input.verdict ?? "gap", tool_status: finding.status,
        note: input.note ?? "", fix: input.fix ?? null, reviewed_at: new Date().toISOString(),
      };
      setAnalysis((a) => (a ? { ...a, reviews: { ...a.reviews, [findingId]: optimistic } } : a));
      try {
        const saved = await api.saveReview(scope, id, findingId, input);
        setAnalysis((a) => (a ? { ...a, reviews: { ...a.reviews, [findingId]: saved } } : a));
      } catch (e) {
        setAnalysis((a) => {
          if (!a) return a;
          const reviews = { ...a.reviews };
          if (before) reviews[findingId] = before;
          else delete reviews[findingId];
          return { ...a, reviews };
        });
        throw e;
      }
    },
    [analysis, id, scope],
  );

  const undo = useCallback(
    async (findingId: string) => {
      await api.clearReview(scope, id, findingId);
      setAnalysis((a) => {
        if (!a) return a;
        const reviews = { ...a.reviews };
        delete reviews[findingId];
        return { ...a, reviews };
      });
    },
    [id, scope],
  );

  return { analysis, error, reload: load, review, undo };
}
