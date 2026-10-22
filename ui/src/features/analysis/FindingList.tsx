import { useEffect, useRef } from "react";
import type { Finding, Review } from "../../api/types";
import { ConfidenceMeter } from "../../components/ConfidenceMeter";
import { ReviewPill, StatusBadge } from "../../components/StatusBadge";
import { docLabel, reviewState } from "../../domain/review";

interface Props {
  findings: Finding[];
  reviews: Record<string, Review>;
  selected: string | null;
  threshold: number;
  onSelect: (id: string) => void;
}

export function FindingList({ findings, reviews, selected, threshold, onSelect }: Props) {
  const active = useRef<HTMLButtonElement>(null);
  // Keep the selection visible inside the scrolling list (desktop); on phones the page itself scrolls.
  useEffect(() => {
    if (window.matchMedia?.("(min-width: 801px)").matches) active.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  if (!findings.length) return <p className="empty">No findings match these filters.</p>;
  return (
    <ul className="finding-list" role="listbox" aria-label="Findings">
      {findings.map((f) => (
        <li key={f.id}>
          <button
            ref={f.id === selected ? active : undefined}
            role="option"
            aria-selected={f.id === selected}
            className={`finding-row ${f.id === selected ? "selected" : ""}`}
            onClick={() => onSelect(f.id)}
            data-testid={`finding-${f.id}`}
          >
            <span className="row-top">
              <StatusBadge status={f.status} />
              <ReviewPill state={reviewState(f, reviews[f.id])} />
            </span>
            <span className="row-title"><code>{f.rule_id}</code> {f.rule_title}</span>
            <span className="row-bottom">
              <span className="truncate muted">{docLabel(f.document)}</span>
              <ConfidenceMeter value={f.confidence} threshold={threshold} compact />
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
