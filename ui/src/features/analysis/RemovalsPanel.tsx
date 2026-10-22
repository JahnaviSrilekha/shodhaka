import { useState } from "react";
import type { Removal } from "../../api/types";

export const REMOVAL_LABEL: Record<Removal["type"], string> = {
  secret: "secret",
  personal: "personal data",
  instruction: "instruction to the AI",
  unsafe: "unsafe language",
};

const ORDER: Removal["type"][] = ["secret", "personal", "instruction", "unsafe"];

/** What was taken out of the analysed copy right after upload, so the person can see it happened. */
export function RemovalsPanel({ removals, document }: { removals: Removal[]; document?: string }) {
  const items = document ? removals.filter((r) => r.document === document) : removals;
  const [open, setOpen] = useState(false);
  const counts = ORDER.map((t) => [t, items.filter((r) => r.type === t).length] as const);

  if (!items.length) {
    return (
      <p className="removals-none muted small" role="status">
        Checked at upload: no secrets, personal data, instructions to the AI or unsafe language found{document ? " in this file" : ""}.
      </p>
    );
  }
  return (
    <section className="card removals" aria-label="Removed before analysis">
      <button className="removals-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <strong>Removed before analysis</strong>
        <span className="badge-row">
          {counts.filter(([, n]) => n).map(([t, n]) => (
            <span key={t} className={`removal-chip removal-${t}`}>{n} {REMOVAL_LABEL[t]}</span>
          ))}
        </span>
        <span className="chev">{open ? "▾" : "▸"}</span>
      </button>
      <p className="muted small">
        Removed from the analysed copy as soon as the file arrived, and marked in the text (REMOVED_…). Rule checks,
        exports and Bedrock only ever see the cleaned text. The original file stays on this machine only.
      </p>
      {open && (
        <table className="table compact">
          <thead><tr>{!document && <th>Document</th>}<th>Line</th><th>Removed</th><th>Preview (masked)</th><th>Found by</th></tr></thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={i}>
                {!document && <td className="truncate">{r.document}</td>}
                <td>{r.line}</td>
                <td><span className={`removal-chip removal-${r.type}`}>{REMOVAL_LABEL[r.type]}</span> {r.label}{r.on_edit ? " (in your edit)" : ""}</td>
                <td><code>{r.preview}</code></td>
                <td className="muted">{r.by}{r.confidence != null ? ` · ${Math.round(r.confidence * 100)}%` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
