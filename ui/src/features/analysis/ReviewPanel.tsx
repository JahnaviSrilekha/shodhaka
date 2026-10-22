import { useEffect, useState } from "react";
import type { Finding, Review, ReviewInput } from "../../api/types";
import { actionsFor, reviewState, TOOL_VERDICT, VERDICT_LABEL } from "../../domain/review";
import { Icon } from "../../components/Icon";
import { ReviewPill } from "../../components/StatusBadge";

interface Props {
  finding: Finding;
  review?: Review;
  onReview: (input: ReviewInput) => Promise<void>;
  onUndo: () => Promise<void>;
}

/** The human decision. Approve agrees with the tool; reject replaces its verdict; the fix text can be edited first. */
export function ReviewPanel({ finding, review, onReview, onUndo }: Props) {
  const showsFix = Boolean(finding.suggested_fix) || finding.status === "gap" || finding.status === "needs_review";
  const [fix, setFix] = useState(review?.fix ?? finding.suggested_fix ?? "");
  const [note, setNote] = useState(review?.note ?? "");
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    setFix(review?.fix ?? finding.suggested_fix ?? "");
    setNote(review?.note ?? "");
  }, [finding.id, review?.fix, review?.note, finding.suggested_fix]);

  const state = reviewState(finding, review);
  const fixEdited = fix.trim() !== (finding.suggested_fix ?? "").trim();

  async function act(key: string, input: ReviewInput) {
    setSaving(key);
    try {
      const keepsFix = (input.verdict ?? TOOL_VERDICT[finding.status]) === "gap";
      await onReview({ ...input, note, fix: keepsFix && fix.trim() ? fix : null });
    } finally {
      setSaving(null);
    }
  }

  return (
    <section className="review-panel" aria-label="Your decision">
      {showsFix && (
        <label className="field">
          <span>
            Suggested fix
            <small className="muted"> · {!finding.suggested_fix ? "the rule has no fix hint: write one" : finding.fix_source === "bedrock" ? "drafted by Bedrock from a redacted snippet" : "from the rule's fix hint"}{fixEdited ? " · edited by you" : ""}</small>
          </span>
          <textarea rows={4} value={fix} onChange={(e) => setFix(e.target.value)} placeholder="Describe the change the document needs" />
        </label>
      )}
      <label className="field">
        <span>Note <small className="muted">(optional, kept with your decision)</small></span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you agree or disagree" />
      </label>

      {review && state !== "pending" ? (
        <div className={`decision decision-${state}`}>
          <ReviewPill state={state} />
          <span>
            {state === "stale"
              ? <>The document was edited and re-checked after you decided <strong>{VERDICT_LABEL[review.verdict].toLowerCase()}</strong>. Decide again.</>
              : <>Final verdict: <strong>{VERDICT_LABEL[review.verdict]}</strong> · {new Date(review.reviewed_at).toLocaleString()}</>}
          </span>
          <button className="button small ghost" onClick={onUndo}><Icon name="undo" /> Undo</button>
        </div>
      ) : null}

      {(!review || state === "stale" || state === "pending") && (
        <div className="decision-buttons">
          {actionsFor(finding).map((a) => (
            <button
              key={a.key}
              className={`button ${a.primary ? "primary" : a.verdict === "gap" ? "danger-outline" : ""}`}
              disabled={saving !== null}
              onClick={() => act(a.key, { decision: a.decision, verdict: a.verdict })}
              title={a.primary ? "Shortcut: A" : undefined}
              data-action={a.primary ? "approve" : undefined}
            >
              {a.primary && <Icon name="check" />} {saving === a.key ? "Saving…" : a.label}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
