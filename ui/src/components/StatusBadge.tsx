import type { Status } from "../api/types";
import { STATUS_LABEL, type ReviewState } from "../domain/review";

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status]}</span>;
}

const STATE_LABEL: Record<ReviewState, string> = {
  pending: "To review",
  approved: "Approved",
  rejected: "Rejected",
  resolved: "Decided",
  stale: "Re-checked",
};

export function ReviewPill({ state }: { state: ReviewState }) {
  return (
    <span className={`pill pill-${state}`} title={state === "stale" ? "The document was edited and re-checked after your decision; decide again" : undefined}>
      {STATE_LABEL[state]}
    </span>
  );
}

export function SeverityTag({ severity }: { severity: string }) {
  return <span className={`severity severity-${severity}`}>{severity}</span>;
}
