import { useEffect, useState } from "react";
import { api, packProblems, type PackScope } from "../../api/client";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { Icon } from "../../components/Icon";
import {
  CHECK_KIND, CHECK_LABEL, emptyPack, KINDS, newRule, standardOptions, toForm, toRaw, type FormPack, type FormRule,
} from "../../domain/packForm";
import { href, navigate } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";

type Tab = "form" | "yaml";

export function PackEditorPage({ scope, packId }: { scope: PackScope; packId: string }) {
  const toast = useToast();
  const creating = packId === "new";
  const [form, setForm] = useState<FormPack | null>(creating ? emptyPack() : null);
  const [yaml, setYaml] = useState("");
  const [tab, setTab] = useState<Tab>("form");
  const [problems, setProblems] = useState<string[]>([]);
  const [checks, setChecks] = useState<string[]>(Object.keys(CHECK_LABEL));
  const [names, setNames] = useState<{ org?: string; project?: string }>({});
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [open, setOpen] = useState(0);

  useEffect(() => {
    api.org(scope.org).then((o) => setNames({ org: o.name, project: o.projects.find((p) => p.id === scope.project)?.name })).catch(() => {});
    if (!creating) {
      api.pack(scope, packId)
        .then((d) => { setForm(toForm(d.pack)); setYaml(d.yaml); setChecks(d.checks); })
        .catch((e) => toast(e.message, "error"));
    }
  }, [scope.org, scope.project, packId]); // eslint-disable-line react-hooks/exhaustive-deps

  const back = scope.project ? href({ page: "project", org: scope.org, project: scope.project }) : href({ page: "org", org: scope.org });
  const change = (next: FormPack) => { setForm(next); setDirty(true); };
  const changeRule = (i: number, patch: Partial<FormRule>) => form && change({ ...form, rules: form.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });

  async function switchTab(next: Tab) {
    if (next === tab || !form) return;
    if (next === "yaml") {
      const out = await api.validatePack({ pack: toRaw(form) });
      setYaml(out.yaml ?? ""); setProblems(out.problems);
    } else {
      const out = await api.validatePack({ yaml });
      if (!out.pack) { setProblems(out.problems); toast("Fix the YAML before switching back to the form", "error"); return; }
      setForm(toForm(out.pack)); setProblems(out.problems);
    }
    setTab(next);
  }

  async function check() {
    if (!form) return;
    const out = await api.validatePack(tab === "yaml" ? { yaml } : { pack: toRaw(form) });
    setProblems(out.problems);
    toast(out.valid ? "The pack is valid" : `${out.problems.length} problem${out.problems.length === 1 ? "" : "s"} found`, out.valid ? "success" : "error");
  }

  async function save() {
    if (!form) return;
    setBusy(true);
    const input = tab === "yaml" ? { yaml } : { pack: toRaw(form) }; // YAML keeps the author's comments
    try {
      const saved = creating ? await api.createPack(scope, input) : await api.updatePack(scope, packId, input);
      setDirty(false); setProblems([]);
      toast(`Saved ${saved.title}`, "success");
      if (creating) navigate({ page: "pack", org: scope.org, project: scope.project, pack: saved.id }, true);
    } catch (e) {
      const list = packProblems(e);
      setProblems(list.length ? list : [(e as Error).message]);
      toast(list.length ? "The pack has problems, see the list" : (e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (!form) return <main className="page"><p className="empty">Loading…</p></main>;
  const level = scope.project ? `project ${names.project ?? ""}` : `all projects of ${names.org ?? "the organization"}`;

  return (
    <main className="page page-medium">
      <Breadcrumbs items={[
        { label: "Organizations", href: "#/" },
        { label: names.org ?? "…", href: href({ page: "org", org: scope.org }) },
        ...(scope.project ? [{ label: names.project ?? "…", href: back }] : []),
        { label: creating ? "New rule pack" : form.title || packId },
      ]} />
      <div className="toolbar">
        <div className="toolbar-title">
          <h1>{creating ? "New rule pack" : form.title || packId}</h1>
          <span className="muted">{scope.project ? "Project rule pack" : "General rule pack"} · applies to {level}{dirty ? " · unsaved changes" : ""}</span>
        </div>
        <div className="toolbar-actions">
          <a className="button ghost" href={back} onClick={(e) => { if (dirty && !window.confirm("Leave without saving?")) e.preventDefault(); }}>Cancel</a>
          <button className="button" onClick={check}>Check</button>
          <button className="button primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save pack"}</button>
        </div>
      </div>

      {problems.length > 0 && (
        <section className="card error-card" role="alert">
          <strong>{problems.length} problem{problems.length === 1 ? "" : "s"}</strong>
          <ul className="problems">{problems.map((p, i) => <li key={i}><code>{p}</code></li>)}</ul>
        </section>
      )}

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "form"} className={tab === "form" ? "active" : ""} onClick={() => switchTab("form")}>Form</button>
        <button role="tab" aria-selected={tab === "yaml"} className={tab === "yaml" ? "active" : ""} onClick={() => switchTab("yaml")}>YAML</button>
      </div>

      {tab === "yaml" ? (
        <section className="card">
          <textarea className="yaml-editor" value={yaml} spellCheck={false} aria-label="Rule pack YAML"
            onChange={(e) => { setYaml(e.target.value); setDirty(true); }} />
          <p className="muted small">Follows specs/contracts/rulepack.schema.json. Comments are kept when you save from this tab.</p>
        </section>
      ) : (
        <>
          <section className="card">
            <div className="form-grid three">
              <label className="field">
                <span>Pack id</span>
                <input value={form.pack} disabled={!creating} onChange={(e) => change({ ...form, pack: e.target.value.toLowerCase() })} placeholder="security-baseline" pattern="[a-z0-9][a-z0-9-]{1,63}" />
                <small className="muted">{creating ? "lower case, digits and dashes; cannot change later" : "cannot change"}</small>
              </label>
              <label className="field"><span>Title</span><input value={form.title} onChange={(e) => change({ ...form, title: e.target.value })} placeholder="Security baseline" /></label>
              <label className="field"><span>Version</span><input value={form.version} onChange={(e) => change({ ...form, version: e.target.value })} /></label>
            </div>
            <label className="field top-gap"><span>Description</span>
              <textarea rows={2} value={form.description} onChange={(e) => change({ ...form, description: e.target.value })} placeholder="What these rules are for" />
            </label>
          </section>

          {form.rules.map((r, i) => (
            <section key={i} className={`card rule-card ${open === i ? "open" : ""}`}>
              <button className="rule-head" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
                <code>{r.id || "(no id)"}</code> <strong>{r.title || "Untitled rule"}</strong>
                <span className="muted small">{r.method === "code" ? CHECK_LABEL[r.check] ?? r.check : "Decider"} · {r.severity}</span>
                <span className="chev">{open === i ? "▾" : "▸"}</span>
              </button>
              {open === i && (
                <div className="rule-body">
                  <div className="form-grid three">
                    <label className="field"><span>Rule id</span><input value={r.id} onChange={(e) => changeRule(i, { id: e.target.value.toUpperCase() })} placeholder="SEC-01" /></label>
                    <label className="field"><span>Title</span><input value={r.title} onChange={(e) => changeRule(i, { title: e.target.value })} /></label>
                    <label className="field"><span>Severity</span>
                      <select value={r.severity} onChange={(e) => changeRule(i, { severity: e.target.value as FormRule["severity"] })}>
                        <option value="high">high</option><option value="medium">medium</option><option value="low">low</option>
                      </select>
                    </label>
                  </div>
                  <label className="field top-gap"><span>Requirement</span>
                    <textarea rows={2} value={r.requirement} onChange={(e) => changeRule(i, { requirement: e.target.value })} placeholder="What a compliant design does, in one or two sentences" />
                  </label>

                  <fieldset className="field top-gap">
                    <legend>How it is checked</legend>
                    <div className="segmented">
                      <label><input type="radio" checked={r.method === "decider"} onChange={() => changeRule(i, { method: "decider", applies_to: ["adr"] })} /> Decider reads the text</label>
                      <label><input type="radio" checked={r.method === "code"} onChange={() => changeRule(i, { method: "code", applies_to: [CHECK_KIND[r.check] ?? "config"] })} /> Code check</label>
                    </div>
                  </fieldset>

                  {r.method === "code" ? (
                    <label className="field top-gap"><span>Check</span>
                      <select value={r.check} onChange={(e) => changeRule(i, { check: e.target.value, applies_to: [CHECK_KIND[e.target.value] ?? "config"] })}>
                        {checks.map((c) => <option key={c} value={c}>{CHECK_LABEL[c] ?? c}</option>)}
                      </select>
                    </label>
                  ) : (
                    <>
                      <label className="field top-gap"><span>Topic <small className="muted">· what a section must be about for this rule to apply (keep it short and specific)</small></span>
                        <input value={r.topic} onChange={(e) => changeRule(i, { topic: e.target.value })} placeholder="which database, schema or tables a service owns, reads or writes" />
                      </label>
                      <label className="field top-gap"><span>Question <small className="muted">· optional, derived from the requirement when empty</small></span>
                        <input value={r.question} onChange={(e) => changeRule(i, { question: e.target.value })} />
                      </label>
                      <div className="form-grid top-gap">
                        <label className="field"><span>Applies per</span>
                          <select value={r.scope} onChange={(e) => changeRule(i, { scope: e.target.value as FormRule["scope"] })}>
                            <option value="section">section (any section can be a gap)</option>
                            <option value="document">document (one compliant section covers it)</option>
                          </select>
                        </label>
                      </div>
                      <div className="field top-gap">
                        <span>Answers Decider chooses from <button className="link-button" onClick={() => changeRule(i, { options: standardOptions() })}>reset to standard</button></span>
                        <table className="table compact options-table">
                          <thead><tr><th>Name</th><th>Verdict</th><th>Description</th><th /></tr></thead>
                          <tbody>
                            {r.options.map((o, k) => (
                              <tr key={k}>
                                <td><input value={o.name} aria-label="Option name" onChange={(e) => changeRule(i, { options: r.options.map((x, m) => (m === k ? { ...x, name: e.target.value.toLowerCase() } : x)) })} /></td>
                                <td>
                                  <select value={o.verdict} aria-label="Verdict" onChange={(e) => changeRule(i, { options: r.options.map((x, m) => (m === k ? { ...x, verdict: e.target.value as typeof o.verdict } : x)) })}>
                                    <option value="compliant">compliant</option><option value="gap">gap</option><option value="not_applicable">not applicable</option>
                                  </select>
                                </td>
                                <td><input value={o.description} aria-label="Option description" onChange={(e) => changeRule(i, { options: r.options.map((x, m) => (m === k ? { ...x, description: e.target.value } : x)) })} /></td>
                                <td><button className="icon-button" aria-label="Remove option" disabled={r.options.length <= 2} onClick={() => changeRule(i, { options: r.options.filter((_, m) => m !== k) })}><Icon name="x" /></button></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <button className="link-button" disabled={r.options.length >= 8} onClick={() => changeRule(i, { options: [...r.options, { name: "", verdict: "gap", description: "" }] })}>+ add answer</button>
                      </div>
                    </>
                  )}

                  <fieldset className="field top-gap">
                    <legend>Checked in</legend>
                    <div className="segmented">
                      {KINDS.map((k) => (
                        <label key={k.value}>
                          <input type="checkbox" checked={r.applies_to.includes(k.value)}
                            onChange={(e) => changeRule(i, { applies_to: e.target.checked ? [...r.applies_to, k.value] : r.applies_to.filter((x) => x !== k.value) })} /> {k.label}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <label className="field top-gap"><span>Fix hint <small className="muted">· shown as the suggested fix (and given to Bedrock)</small></span>
                    <input value={r.fix_hint} onChange={(e) => changeRule(i, { fix_hint: e.target.value })} />
                  </label>
                  <div className="actions-row top-gap">
                    <button className="button small danger-outline" disabled={form.rules.length <= 1} onClick={() => { change({ ...form, rules: form.rules.filter((_, j) => j !== i) }); setOpen(-1); }}>Remove rule</button>
                  </div>
                </div>
              )}
            </section>
          ))}
          <button className="button" onClick={() => { change({ ...form, rules: [...form.rules, newRule(form.rules)] }); setOpen(form.rules.length); }}>+ Add rule</button>
        </>
      )}
    </main>
  );
}
