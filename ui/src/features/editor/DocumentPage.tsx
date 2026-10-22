import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Scope } from "../../api/client";
import type { DocumentText } from "../../api/types";
import { Icon } from "../../components/Icon";
import { ReviewPill, StatusBadge } from "../../components/StatusBadge";
import { docLabel, insertAt, insertionLine, lineEndOffset, reviewState, sortForReview, targetHeading, touches } from "../../domain/review";
import { useAnalysis } from "../../hooks/useAnalysis";
import { href, navigate } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";
import { RemovalsPanel } from "../analysis/RemovalsPanel";

const LINE_HEIGHT = 21; // px, must match .editor line-height

export function DocumentPage({ scope, id, path, findingId }: { scope: Scope; id: string; path: string; findingId?: string }) {
  const toast = useToast();
  const { analysis } = useAnalysis(scope, id);
  const [doc, setDoc] = useState<DocumentText | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<null | "save" | "recheck">(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const dirty = doc !== null && text !== doc.text;

  useEffect(() => {
    api.document(scope, id, path).then((d) => { setDoc(d); setText(d.text); }).catch((e) => toast(e.message, "error"));
  }, [scope.org, scope.project, id, path, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const findings = useMemo(
    () => sortForReview(analysis?.report?.findings.filter((f) => touches(f, path)) ?? []),
    [analysis, path],
  );
  const lines = useMemo(() => text.split("\n").length, [text]);
  const sectionsWithFindings = useMemo(() => {
    const map = new Map<string, string[]>();
    findings.filter((f) => f.status === "gap" || f.status === "needs_review").forEach((f) => {
      const heading = targetHeading(f, path);
      if (heading) map.set(heading, [...(map.get(heading) ?? []), f.rule_id]);
    });
    return map;
  }, [findings]);

  const goToLine = useCallback((line: number) => {
    const area = editor.current;
    if (!area) return;
    const offset = text.split("\n").slice(0, line - 1).join("\n").length + (line > 1 ? 1 : 0);
    area.focus();
    area.setSelectionRange(offset, offset);
    area.scrollTop = Math.max(0, (line - 3) * LINE_HEIGHT);
  }, [text]);

  // Start with the cursor at the end of the section the finding is about (its evidence, or the
  // section Decider found most on-topic). The reviewer moves it if the fix belongs elsewhere.
  const jumped = useRef(false);
  useEffect(() => {
    if (jumped.current || !doc || !findingId || !editor.current) return;
    const f = findings.find((x) => x.id === findingId);
    if (!f) return;
    jumped.current = true;
    const heading = targetHeading(f, path);
    const section = doc.sections.find((s) => s.heading === heading);
    if (!section) {
      if (f.evidence[0]?.line) goToLine(f.evidence[0].line);
      return;
    }
    const end = lineEndOffset(text, insertionLine(text, doc.sections, heading));
    const area = editor.current;
    area.focus();
    area.setSelectionRange(end, end);
    area.scrollTop = Math.max(0, (section.start_line - 3) * LINE_HEIGHT);
  }, [doc, findingId, findings, goToLine, text]);

  async function save(andRecheck: boolean) {
    setBusy(andRecheck ? "recheck" : "save");
    try {
      let current = doc;
      if (dirty) {
        current = await api.saveDocument(scope, id, path, text);
        setDoc(current);
        setText(current.text);
      }
      if (andRecheck) {
        await api.recheck(scope, id, path);
        toast("Re-checking with Decider…", "info");
        navigate({ page: "analysis", ...scope, id, finding: findingId });
      } else {
        toast("Saved. Re-check to update the findings.", "success");
      }
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  function applyFix(fid: string) {
    const f = findings.find((x) => x.id === fid);
    if (!f || !doc) return;
    const fix = analysis?.reviews[fid]?.fix ?? f.suggested_fix;
    if (!fix) return;
    const area = editor.current;
    const result = insertAt(text, area ? area.selectionStart : text.length, f, fix);
    setText(result.text);
    window.requestAnimationFrame(() => { area?.focus(); area?.setSelectionRange(result.cursor, result.cursor); });
    toast(f.scope === "document"
      ? `Inserted the ${f.rule_id} fix at your cursor. ${f.rule_id} counts for the whole document, so any section is fine.`
      : `Inserted the ${f.rule_id} fix at your cursor. Edit it, then save and re-check.`, "success");
  }

  function leave() {
    if (dirty && !window.confirm("You have unsaved changes. Leave without saving?")) return;
    location.hash = href({ page: "analysis", ...scope, id, finding: findingId });
  }

  if (!doc) return <main className="page"><p className="empty">Loading document…</p></main>;
  const convertible = doc.kind === "adr" && doc.original_format !== "md" && doc.original_format !== "markdown";

  return (
    <main className="page page-wide">
      <div className="toolbar">
        <button className="button ghost" onClick={leave}><Icon name="back" /> Back to review</button>
        <div className="toolbar-title">
          <h1 className="truncate">{path}</h1>
          <span className="muted">
            {dirty ? "Unsaved changes" : doc.edited ? "Edited · not re-checked yet" : "As uploaded"}
            {convertible && " · text extracted from " + doc.original_format.toUpperCase() + ", downloads as Markdown"}
          </span>
        </div>
        <div className="toolbar-actions">
          <button className="button ghost" disabled={!dirty || busy !== null} onClick={() => setText(doc.text)}>Revert</button>
          <a className="button" href={api.exportUrl.document(scope, id, path)} download aria-disabled={dirty}><Icon name="download" /> Download</a>
          <button className="button" disabled={!dirty || busy !== null} onClick={() => save(false)}>{busy === "save" ? "Saving…" : "Save"}</button>
          <button className="button primary" disabled={busy !== null || (!dirty && !doc.edited)} onClick={() => save(true)}
            title={!dirty && !doc.edited ? "Edit the document first" : "Save and run Decider on this document again"}>
            <Icon name="refresh" /> {busy === "recheck" ? "Starting…" : "Save & re-check"}
          </button>
        </div>
      </div>

      <div className="editor-layout">
        <nav className="sidebar" aria-label="Sections">
          <h2 className="sidebar-title">Sections</h2>
          {doc.sections.map((s) => (
            <button key={s.id} className="doc-item" onClick={() => goToLine(s.start_line)}>
              <span className="truncate">{s.heading}</span>
              {sectionsWithFindings.get(s.heading)?.map((r) => <span key={r} className="tag tag-alert">{r}</span>)}
            </button>
          ))}
        </nav>

        <div className="editor-frame">
          <div className="gutter" ref={gutter} aria-hidden>
            {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
          </div>
          <textarea
            ref={editor}
            className="editor"
            value={text}
            spellCheck={doc.kind === "adr"}
            onChange={(e) => setText(e.target.value)}
            onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop; }}
            aria-label={`Contents of ${path}`}
          />
        </div>

        <aside className="side-findings" aria-label="Findings in this document">
          {analysis?.removals && <RemovalsPanel removals={analysis.removals} document={path} />}
          <h2 className="sidebar-title">Findings here</h2>
          <p className="muted small hint-text">Click in the text where a fix belongs, then “Insert at cursor”.</p>
          {findings.map((f) => {
            const fix = analysis?.reviews[f.id]?.fix ?? f.suggested_fix;
            return (
              <div key={f.id} className={`mini-finding ${f.id === findingId ? "selected" : ""}`}>
                <div className="row-top">
                  <StatusBadge status={f.status} />
                  <ReviewPill state={reviewState(f, analysis?.reviews[f.id])} />
                </div>
                <a href={href({ page: "analysis", ...scope, id, finding: f.id })}><code>{f.rule_id}</code> {f.rule_title}</a>
                {f.document !== path && <span className="muted small">{docLabel(f.document)} · judged together</span>}
                {(f.status === "gap" || f.status === "needs_review") && fix && (
                  <>
                    <p className="mini-fix">{fix}</p>
                    {doc.kind === "adr" ? (
                      <button className="button small" onClick={() => applyFix(f.id)} title="Click in the document where the fix belongs first"><Icon name="edit" /> Insert at cursor</button>
                    ) : (
                      <span className="muted small">Edit the file directly, then re-check.</span>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </aside>
      </div>
    </main>
  );
}
