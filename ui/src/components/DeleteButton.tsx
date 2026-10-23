import { useState } from "react";
import { Icon } from "./Icon";

/** Two-step delete without a browser dialog: the first click asks, the second one deletes. */
export function DeleteButton({ what, detail, onDelete }: { what: string; detail: string; onDelete: () => Promise<void> }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!asking) {
    return (
      <button className="button small danger-outline" onClick={() => setAsking(true)}>
        <Icon name="x" /> Delete {what}
      </button>
    );
  }
  return (
    <div className="confirm-delete" role="alert">
      <span>{detail}</span>
      <button className="button small danger-outline" disabled={busy}
        onClick={async () => { setBusy(true); try { await onDelete(); } finally { setBusy(false); setAsking(false); } }}>
        {busy ? "Deleting…" : `Yes, delete ${what}`}
      </button>
      <button className="button small ghost" disabled={busy} onClick={() => setAsking(false)}>Cancel</button>
    </div>
  );
}
