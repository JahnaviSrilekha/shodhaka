import { useEffect, useMemo, useReducer } from "react";
import { api, type Scope } from "../../api/client";
import type { ReviewInput } from "../../api/types";
import { Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { applyFilter, progress, reviewState, STATUS_ORDER } from "../../domain/review";
import { DESIGN_SET } from "../../api/types";
import { useAnalysis } from "../../hooks/useAnalysis";
import { href, navigate } from "../../hooks/useHashRoute";
import { useHotkeys } from "../../hooks/useHotkeys";
import { useToast } from "../../hooks/useToast";
import { FindingDetail } from "./FindingDetail";
import { FindingList } from "./FindingList";
import { RemovalsPanel } from "./RemovalsPanel";
import { UsagePanel } from "./UsagePanel";
import { filterReducer, initialFilter } from "./filters";

export function AnalysisPage({ scope, id, findingId }: { scope: Scope; id: string; findingId?: string }) {
  const toast = useToast();
  const { analysis, error, review, undo } = useAnalysis(scope, id);
  const [filter, dispatch] = useReducer(filterReducer, initialFilter);

  const report = analysis?.report ?? null;
  const reviews = analysis?.reviews ?? {};
  const visible = useMemo(() => (report ? applyFilter(report.findings, reviews, filter) : []), [report, reviews, filter]);
  const selected = report?.findings.find((f) => f.id === findingId) ?? visible[0] ?? null;
  const done = report ? progress(report.findings, reviews) : null;

  const select = (fid: string) => navigate({ page: "analysis", ...scope, id, finding: fid }, true);
  const move = (step: number) => {
    if (!visible.length) return;
    const at = selected ? visible.findIndex((f) => f.id === selected.id) : -1;
    select(visible[Math.min(visible.length - 1, Math.max(0, at + step))].id);
  };
  const nextOpen = () => {
    const at = selected ? visible.findIndex((f) => f.id === selected.id) : -1;
    const next = [...visible.slice(at + 1), ...visible.slice(0, at + 1)].find(
      (f) => f.id !== selected?.id && ["pending", "stale"].includes(reviewState(f, reviews[f.id])),
    );
    if (next) select(next.id);
  };

  async function onReview(input: ReviewInput) {
    if (!selected) return;
    try {
      await review(selected.id, input);
      nextOpen();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  useHotkeys({
    j: () => move(1),
    k: () => move(-1),
    ArrowDown: () => move(1),
    ArrowUp: () => move(-1),
    a: () => document.querySelector<HTMLButtonElement>("[data-action=approve]")?.click(),
    e: () => selected && navigate({ page: "document", ...scope, id, path: selected.document, finding: selected.id }),
  }, Boolean(report));

  useEffect(() => {
    if (analysis?.status === "failed") toast(analysis.error ?? "Analysis failed", "error");
  }, [analysis?.status, analysis?.error, toast]);

  if (error) return <main className="page"><p className="empty">Could not load this analysis: {error}</p></main>;
  if (!analysis) return <main className="page"><p className="empty">Loading…</p></main>;

  const running = analysis.status === "queued" || analysis.status === "cleaning" || analysis.status === "running";
  const docCounts = (doc: string) => report?.findings.filter((f) => f.document === doc && (f.status === "gap" || f.status === "needs_review")).length ?? 0;

  return (
    <main className="page page-wide">
      <div className="toolbar">
        <a className="button ghost" href={href({ page: "project", ...scope })}><Icon name="back" /> Project</a>
        <div className="toolbar-title">
          <h1>Review</h1>
          <span className="muted" title={`Rule packs: ${(analysis.packs ?? []).join(", ")}`}>{analysis.mode === "design-set" ? "one design across documents · " : ""}{analysis.pack} · gate {Math.round(analysis.threshold * 100)}% · {analysis.documents.length} document{analysis.documents.length === 1 ? "" : "s"}</span>
        </div>
        {report && (
          <div className="toolbar-actions">
            <span className="progress-label" aria-label="Review progress">
              <span className="progress"><span style={{ width: `${done!.percent}%` }} /></span>
              {done!.done}/{done!.total} reviewed
            </span>
            <a className="button" href={api.exportUrl.expected(scope, id)} download title="Your verdicts, ready for: shodhaka eval report.json expected.json">
              <Icon name="download" /> expected.json
            </a>
            <a className="button" href={api.exportUrl.report(scope, id)} download><Icon name="download" /> Report</a>
            <a className="button ghost" href={api.exportUrl.rules(scope, id)} download title="The exact rules this analysis ran with">Rules</a>
          </div>
        )}
      </div>

      {running && (
        <section className="card running" aria-live="polite">
          <div className="spinner" aria-hidden />
          <div>
            {analysis.status === "cleaning" ? (
              <>
                <strong>Removing unsafe language from {analysis.progress.current ?? "the documents"}…</strong>
                <div className="muted">Before any rule is checked · {analysis.progress.done} of {analysis.progress.total} documents · Decider, locally</div>
              </>
            ) : (
              <>
                <strong>Decider is reading {analysis.progress.current ?? "the documents"}…</strong>
                <div className="muted">{analysis.progress.done} of {analysis.progress.total} documents done · each section gets a yes/no per rule, locally</div>
              </>
            )}
            <span className="progress wide"><span style={{ width: `${analysis.progress.total ? (analysis.progress.done / analysis.progress.total) * 100 : 0}%` }} /></span>
          </div>
        </section>
      )}
      {analysis.removals && analysis.status !== "queued" && <RemovalsPanel removals={analysis.removals} />}
      {analysis.usage && <UsagePanel usage={analysis.usage} bedrockOn={analysis.bedrock} />}
      {analysis.status === "failed" && (
        <section className="card error-card"><strong>The analysis stopped.</strong> {analysis.error}</section>
      )}

      {report && (
        <div className="review-layout">
          <aside className="sidebar" aria-label="Documents">
            <h2 className="sidebar-title">Documents</h2>
            <button className={`doc-item ${filter.document === null ? "active" : ""}`} onClick={() => dispatch({ type: "document", document: null })}>
              All documents <span className="count">{report.findings.filter((f) => f.status === "gap" || f.status === "needs_review").length}</span>
            </button>
            {report.mode === "design-set" && (
              <button className={`doc-item ${filter.document === DESIGN_SET ? "active" : ""}`} onClick={() => dispatch({ type: "document", document: DESIGN_SET })}
                title={`Judged together: ${(report.design_set ?? []).join(", ")}`}>
                <span className="truncate">All design documents ({report.design_set?.length ?? 0})</span>
                {docCounts(DESIGN_SET) > 0 && <span className="count count-alert">{docCounts(DESIGN_SET)}</span>}
              </button>
            )}
            {report.documents.map((doc) => (
              <div key={doc} className={`doc-item-row ${filter.document === doc ? "active" : ""}`}>
                <button className="doc-item" onClick={() => dispatch({ type: "document", document: doc })} title={doc}>
                  <span className="truncate">{doc}</span>
                  {analysis.edited.includes(doc) && <span className="tag">edited</span>}
                  {docCounts(doc) > 0 && <span className="count count-alert">{docCounts(doc)}</span>}
                </button>
                <a className="icon-button" href={href({ page: "document", ...scope, id, path: doc })} aria-label={`Open ${doc}`}><Icon name="edit" /></a>
              </div>
            ))}
            {analysis.skipped.length > 0 && (
              <p className="muted small">Skipped: {analysis.skipped.map((s) => `${s.file} (${s.reason})`).join("; ")}</p>
            )}
          </aside>

          <section className="list-pane" aria-label="Findings">
            <div className="filters">
              {STATUS_ORDER.map((s) => (
                <button key={s} className={`chip ${filter.statuses.has(s) ? "chip-on" : ""}`} aria-pressed={filter.statuses.has(s)}
                  onClick={() => dispatch({ type: "toggleStatus", status: s })}>
                  <StatusBadge status={s} /> {report.summary[s]}
                </button>
              ))}
            </div>
            <div className="filters">
              <label className="search">
                <Icon name="search" />
                <input placeholder="Search rule, document, evidence" value={filter.query} onChange={(e) => dispatch({ type: "query", value: e.target.value })} />
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={filter.onlyOpen} onChange={(e) => dispatch({ type: "onlyOpen", value: e.target.checked })} /> Open only
              </label>
            </div>
            <FindingList findings={visible} reviews={reviews} selected={selected?.id ?? null} threshold={report.threshold}
              onSelect={(fid) => {
                select(fid);
                if (!window.matchMedia?.("(min-width: 801px)").matches)
                  window.setTimeout(() => document.querySelector(".detail-pane")?.scrollIntoView({ behavior: "smooth" }), 50);
              }} />
            <p className="hint muted"><kbd>J</kbd>/<kbd>K</kbd> move · <kbd>A</kbd> approve · <kbd>E</kbd> edit document</p>
          </section>

          <section className="detail-pane">
            {selected ? (
              <FindingDetail
                key={selected.id}
                scope={scope}
                analysisId={id}
                finding={selected}
                review={reviews[selected.id]}
                threshold={report.threshold}
                onReview={onReview}
                onUndo={() => undo(selected.id).catch((e) => toast(e.message, "error"))}
              />
            ) : (
              <p className="empty">Select a finding.</p>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
