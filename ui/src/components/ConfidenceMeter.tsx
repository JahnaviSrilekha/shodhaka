/** Confidence against the gate: the tick marks the threshold, so "why was this escalated" is visible. */
export function ConfidenceMeter({ value, threshold, compact = false }: { value: number; threshold: number; compact?: boolean }) {
  const pct = Math.round(value * 100);
  const below = value < threshold;
  return (
    <span className={`meter ${compact ? "meter-compact" : ""}`} title={`Confidence ${pct}% · gate ${Math.round(threshold * 100)}%`}>
      <span className="meter-track" aria-hidden>
        <span className={`meter-fill ${below ? "meter-low" : ""}`} style={{ width: `${pct}%` }} />
        <span className="meter-gate" style={{ left: `${threshold * 100}%` }} />
      </span>
      <span className="meter-value">{pct}%</span>
    </span>
  );
}
