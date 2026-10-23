import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Scope } from "../../api/client";
import type { AnalysisMode, Candidate, Health, Recommendation } from "../../api/types";
import { ids, modeExplanation, plan } from "../../domain/analysisPlan";
import { clashes, selectedRules, SOURCE_LABEL } from "../../domain/packSelection";
import { navigate } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";
import { Dropzone, isSupported } from "../upload/Dropzone";

interface Props {
  scope: Scope;
  health: Health | null;
}

type RecState = { status: "idle" | "loading" | "done" | "unavailable"; data?: Recommendation; error?: string };

/**
 * Nothing runs before the person confirms:
 *  1. choose files; Decider suggests rule packs from the start of each document (read-only);
 *     the person ticks the packs to use and, with 2+ design documents, says how they relate;
 *  2. a summary of exactly what will be checked and how; then start.
 */
export function NewAnalysis({ scope, health }: Props) {
  const toast = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [useBedrock, setUseBedrock] = useState(false);
  const [mode, setMode] = useState<AnalysisMode | null>(null);
  const [step, setStep] = useState<"setup" | "confirm">("setup");
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [touched, setTouched] = useState(false); // the person changed the ticks: keep their choice
  const [rec, setRec] = useState<RecState>({ status: "idle" });
  const requestId = useRef(0);

  useEffect(() => { if (health && threshold === null) setThreshold(health.default_threshold); }, [health, threshold]);
  useEffect(() => {
    api.candidates(scope).then((c) => {
      setCandidates(c);
      setSelected(c.filter((x) => x.in_effect).map((x) => x.ref)); // until a recommendation arrives: the project's rules
    }).catch((e) => toast(e.message, "error"));
  }, [scope.org, scope.project]); // eslint-disable-line react-hooks/exhaustive-deps

  const usable = useMemo(() => files.filter((f) => isSupported(f.name)), [files]);
  const fileKey = usable.map((f) => `${f.name}:${f.size}`).join("|");

  // Ask Decider which packs fit, whenever the file selection changes (read-only, nothing is stored).
  useEffect(() => {
    setStep("setup");
    if (!usable.length) { setRec({ status: "idle" }); return; }
    if (health?.decider !== "up") { setRec({ status: "unavailable", error: "Decider is offline" }); return; }
    const id = ++requestId.current;
    setRec({ status: "loading" });
    const timer = window.setTimeout(() => {
      api.recommend(scope, usable)
        .then((data) => {
          if (id !== requestId.current) return;
          setRec({ status: "done", data });
          setCandidates(data.candidates);
          if (!touched && data.recommended.length) setSelected(data.recommended);
        })
        .catch((e: Error) => id === requestId.current && setRec({ status: "unavailable", error: e.message }));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [fileKey, health?.decider]); // eslint-disable-line react-hooks/exhaustive-deps

  const rules = useMemo(() => selectedRules(candidates, selected), [candidates, selected]);
  const problems = useMemo(() => clashes(candidates, selected), [candidates, selected]);
  const p = useMemo(() => plan(usable.map((f) => f.name), rules), [usable, rules]);
  useEffect(() => { if (!p.needsChoice) setMode(null); }, [p.needsChoice]);
  const effectiveMode: AnalysisMode = p.needsChoice ? mode ?? "per-document" : "per-document";
  const gate = threshold ?? 0.75;
  const chosen = candidates.filter((c) => selected.includes(c.ref));
  const blocked = !usable.length || busy || health?.decider === "down" || !rules.length || problems.length > 0
    || (p.needsChoice && mode === null);

  const toggle = (ref: string, on: boolean) => {
    setTouched(true);
    setSelected((s) => (on ? [...s, ref] : s.filter((x) => x !== ref)));
  };
  const why = (ref: string) => rec.data?.packs.find((x) => x.ref === ref);

  async function start() {
    setBusy(true);
    try {
      const meta = await api.createAnalysis(scope, usable, gate, useBedrock, effectiveMode, selected);
      if (meta.skipped.length) toast(`Skipped ${meta.skipped.map((s) => s.file).join(", ")}`, "info");
      (meta.notes ?? []).forEach((n) => toast(n, "info"));
      navigate({ page: "analysis", ...scope, id: meta.id });
    } catch (e) {
      toast((e as Error).message, "error");
      setBusy(false);
    }
  }

  if (step === "confirm") {
    return (
      <section className="card confirm-card" aria-labelledby="confirm-title">
        <h2 className="card-title" id="confirm-title">Check before starting</h2>
        <ul className="plan">
          <li>
            <strong>{chosen.length} rule pack{chosen.length === 1 ? "" : "s"}, {rules.length} rules</strong>
            {chosen.map((c) => (
              <div key={c.ref} className="plan-line">
                {c.title} <span className="muted small">· {SOURCE_LABEL[c.source]}{rec.data?.recommended.includes(c.ref) ? " · recommended" : ""}</span>
              </div>
            ))}
          </li>
          {p.designDocs.length > 0 && (
            <li>
              <strong>{p.designDocs.length} design / policy document{p.designDocs.length === 1 ? "" : "s"}</strong>
              {p.needsChoice && <span className={`mode-tag mode-${effectiveMode}`}>{effectiveMode === "design-set" ? "one design" : "separate"}</span>}
              <div className="muted small">{p.designDocs.join(", ")}</div>
              {(p.needsChoice ? modeExplanation(p, effectiveMode) : ["Checked section by section against every rule for documents."]).map((line) => (
                <div key={line} className="plan-line">{line}</div>
              ))}
            </li>
          )}
          {p.codeFiles.length > 0 && (
            <li>
              <strong>{p.codeFiles.length} config / Docker file{p.codeFiles.length === 1 ? "" : "s"}</strong>
              <div className="muted small">{p.codeFiles.join(", ")}</div>
              <div className="plan-line">Always checked file by file{p.codeRules.length ? ` by code: ${ids(p.codeRules)}` : " (no code rules ticked: nothing to check)"}.</div>
            </li>
          )}
          <li>
            <strong>Confidence gate {Math.round(gate * 100)}%</strong>
            <div className="plan-line">
              Right after upload, secrets, personal data, instructions aimed at the AI and unsafe language are removed from the
              copy that gets analysed; you will see a list of every removal. The original files stay on this machine only.
            </div>
            <div className="plan-line">
              {useBedrock ? "Bedrock drafts fixes from redacted snippets; full documents stay on this machine." : "Nothing leaves this machine."}
              {" "}Every finding waits for your approval.
            </div>
          </li>
        </ul>
        <div className="actions-row">
          <button className="button ghost" onClick={() => setStep("setup")} disabled={busy}>Back</button>
          <button className="button primary" onClick={start} disabled={busy}>{busy ? "Uploading…" : "Start analysis"}</button>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <h2 className="card-title">New analysis</h2>
      <Dropzone files={files} onChange={setFiles} />

      {usable.length > 0 && (
        <fieldset className="relation" aria-describedby="packs-help">
          <legend>Rule packs to check against</legend>
          <p id="packs-help" className="muted small" aria-live="polite">
            {rec.status === "loading" && "Decider is reading the start of each document to suggest packs…"}
            {rec.status === "done" && (rec.data!.recommended.length
              ? "Suggested from the start of each document (read locally, nothing stored). Change the ticks if they are wrong."
              : "No pack clearly fits these documents. Tick the ones to use.")}
            {rec.status === "unavailable" && `No suggestion (${rec.error}). Tick the packs to use.`}
          </p>
          {candidates.map((c) => {
            const reason = why(c.ref);
            const recommended = rec.data?.recommended.includes(c.ref);
            return (
              <label key={c.ref} className={`choice ${selected.includes(c.ref) ? "chosen" : ""}`}>
                <input type="checkbox" checked={selected.includes(c.ref)} onChange={(e) => toggle(c.ref, e.target.checked)} />
                <span>
                  <strong>
                    {c.title} {recommended && <span className="rec-tag">Recommended</span>}
                  </strong>
                  <span className="muted small">
                    {SOURCE_LABEL[c.source]} · {c.rules.length} rules
                    {reason?.picked_by.length ? ` · fits ${reason.picked_by.join(", ")}` : ""}
                  </span>
                </span>
              </label>
            );
          })}
          {touched && rec.data?.recommended.length ? (
            <button className="link-button" onClick={() => { setSelected(rec.data!.recommended); setTouched(false); }}>Use the suggestion again</button>
          ) : null}
          {problems.map((x) => <span key={x} className="warn small">{x}: untick one of them.</span>)}
        </fieldset>
      )}

      {p.needsChoice && (
        <fieldset className="relation" aria-describedby="relation-help">
          <legend>How are these {p.designDocs.length} documents related? <span className="required">required</span></legend>
          <p id="relation-help" className="muted small">This decides whether a rule has to be met in every document or once across all of them.</p>
          <label className={`choice ${mode === "per-document" ? "chosen" : ""}`}>
            <input type="radio" name="mode" checked={mode === "per-document"} onChange={() => setMode("per-document")} />
            <span>
              <strong>Separate documents</strong>
              <span className="muted small">Each document must meet every rule on its own. Use for unrelated documents or ADRs that each stand alone.</span>
            </span>
          </label>
          <label className={`choice ${mode === "design-set" ? "chosen" : ""}`}>
            <input type="radio" name="mode" checked={mode === "design-set"} onChange={() => setMode("design-set")} />
            <span>
              <strong>One design (or policy set) split across documents</strong>
              <span className="muted small">
                Read together.{p.presence.length ? ` ${ids(p.presence)} count${p.presence.length === 1 ? "s" : ""} if met in any document.` : ""}
                {p.prohibition.length ? ` ${ids(p.prohibition)} ${p.prohibition.length === 1 ? "is" : "are"} a gap if any document breaks ${p.prohibition.length === 1 ? "it" : "them"}.` : ""}
              </span>
            </span>
          </label>
        </fieldset>
      )}

      <div className="form-grid analysis-options">
        <label className="field">
          <span>Confidence gate <strong>{Math.round(gate * 100)}%</strong></span>
          <input type="range" min={0.5} max={0.99} step={0.01} value={gate} onChange={(e) => setThreshold(Number(e.target.value))} aria-label="Confidence gate" />
          <small className="muted">Higher sends more findings to you as “Needs review”.</small>
        </label>
        <label className={`checkbox ${health?.bedrock ? "" : "disabled"}`}>
          <input type="checkbox" checked={useBedrock} disabled={!health?.bedrock} onChange={(e) => setUseBedrock(e.target.checked)} />
          Draft fixes with Amazon Bedrock (redacted snippets only)
          {!health?.bedrock && <small className="muted"> · start the server with --bedrock</small>}
        </label>
      </div>
      <div className="actions-row">
        {health?.decider === "down" && <span className="warn">Decider is offline: start it first.</span>}
        {usable.length > 0 && !rules.length && <span className="warn">Tick at least one rule pack.</span>}
        {p.needsChoice && mode === null && usable.length > 0 && <span className="warn">Choose how the documents are related.</span>}
        <button className="button primary" disabled={blocked} onClick={() => setStep("confirm")}>
          Review and start ({usable.length} file{usable.length === 1 ? "" : "s"})
        </button>
      </div>
    </section>
  );
}
