import { useState } from "react";
import type { Finding, Review, ReviewInput } from "../../api/types";
import { ConfidenceMeter } from "../../components/ConfidenceMeter";
import { Icon } from "../../components/Icon";
import { SeverityTag, StatusBadge } from "../../components/StatusBadge";
import { href } from "../../hooks/useHashRoute";
import type { Scope } from "../../api/client";
import { ReviewPanel } from "./ReviewPanel";
import { isDesignSet } from "../../domain/review";

interface Props {
  scope: Scope;
  analysisId: string;
  finding: Finding;
  review?: Review;
  threshold: number;
  onReview: (input: ReviewInput) => Promise<void>;
  onUndo: () => Promise<void>;
}

export function FindingDetail({ scope, analysisId, finding, review, threshold, onReview, onUndo }: Props) {
  const [showSections, setShowSections] = useState(false);
  const inSet = isDesignSet(finding);
  const docs = inSet ? finding.documents ?? [] : [finding.document];
  // the document to open for editing: where the problem is quoted, else the first of the set
  const editDoc = finding.evidence.find((e) => e.role !== "meets" && e.document)?.document
    ?? finding.evidence.find((e) => e.document)?.document ?? docs[0];
  const where = (e: (typeof finding.evidence)[number]) =>
    [inSet ? e.document : null, e.section ?? (e.line ? `line ${e.line}` : null)].filter(Boolean).join(" › ");

  return (
    <article className="detail" aria-labelledby="detail-title">
      <header className="detail-header">
        <div className="detail-meta">
          <StatusBadge status={finding.status} />
          <SeverityTag severity={finding.severity} />
          <span className="muted">
            {finding.decided_by === "code" ? "checked by code"
              : inSet ? `Decider · ${finding.scope === "document" ? "met if any document has it" : "a gap if any document breaks it"}`
              : `Decider · ${finding.scope === "document" ? "whole document" : "per section"}`}
          </span>
          {finding.rule_source && (
            <span className={`source source-${finding.rule_source.scope}`} title={finding.rule_source.overrides ? `replaces the rule from ${finding.rule_source.overrides}` : undefined}>
              {finding.rule_source.scope === "project" ? "Project rule" : finding.rule_source.scope === "template" ? "Template rule" : "Organization rule"} · {finding.rule_source.pack}
            </span>
          )}
        </div>
        <h2 id="detail-title"><code>{finding.rule_id}</code> {finding.rule_title}</h2>
        {inSet ? (
          <div className="doc-links">
            <span className="muted small">Design set of {docs.length}:</span>
            {docs.map((d) => (
              <a key={d} className="doc-link" href={href({ page: "document", ...scope, id: analysisId, path: d, finding: finding.id })}><Icon name="doc" /> {d}</a>
            ))}
          </div>
        ) : (
          <a className="doc-link" href={href({ page: "document", ...scope, id: analysisId, path: finding.document, finding: finding.id })}>
            <Icon name="doc" /> {finding.document}
          </a>
        )}
      </header>

      <div className="detail-row">
        <span className="label">Confidence</span>
        <ConfidenceMeter value={finding.confidence} threshold={threshold} />
      </div>
      {finding.reason && <p className="reason">{finding.reason}</p>}

      <section>
        <h3 className="section-title">Evidence</h3>
        {finding.evidence.length ? finding.evidence.map((e, i) => (
          <div key={i} className="evidence-item">
            <div className="muted small">
              {e.role === "breaks" && <span className="role role-breaks">breaks the rule</span>}
              {e.role === "meets" && <span className="role role-meets">meets the rule</span>}
              {where(e)}
            </div>
            <blockquote className={`evidence ${e.role === "meets" ? "evidence-meets" : ""}`}>{e.text}</blockquote>
          </div>
        )) : (
          <p className="muted">No quote: the rule's topic was not found {inSet ? "in any of the documents" : "in this document"}.</p>
        )}
      </section>

      {finding.sections.length > 0 && (
        <section>
          <button className="disclosure" aria-expanded={showSections} onClick={() => setShowSections((s) => !s)}>
            {showSections ? "▾" : "▸"} Decider's answer per section ({finding.sections.length})
          </button>
          {showSections && (
            <table className="table compact">
              <thead><tr><th>Section</th><th>Answer</th><th>Confidence</th></tr></thead>
              <tbody>
                {finding.sections.map((s) => (
                  <tr key={s.section}>
                    <td>{s.heading}</td>
                    <td><span className={`verdict verdict-${s.verdict}`}>{s.verdict.replace("_", " ")}</span></td>
                    <td><ConfidenceMeter value={s.confidence} threshold={threshold} compact /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      <ReviewPanel finding={finding} review={review} onReview={onReview} onUndo={onUndo} />

      <footer className="detail-footer">
        <a className="button" href={href({ page: "document", ...scope, id: analysisId, path: editDoc, finding: finding.id })}>
          <Icon name="edit" /> Edit {inSet ? editDoc : "document"} and re-check
        </a>
      </footer>
    </article>
  );
}
