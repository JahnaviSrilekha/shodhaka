import { api, type Scope } from "../../api/client";
import type { Health } from "../../api/types";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { StatusBadge, SeverityTag } from "../../components/StatusBadge";
import { STATUS_ORDER } from "../../domain/review";
import { href } from "../../hooks/useHashRoute";
import { useLoad } from "../../hooks/useLoad";
import { useToast } from "../../hooks/useToast";
import { PackList } from "../packs/PackList";
import { NewAnalysis } from "./NewAnalysis";

const KIND_LABEL: Record<string, string> = { adr: "design docs", config: "config", dockerfile: "Dockerfiles" };

export function ProjectPage({ scope, health }: { scope: Scope; health: Health | null }) {
  const toast = useToast();
  const project = useLoad(() => api.project(scope), [scope.org, scope.project]);
  const analyses = useLoad(() => api.analyses(scope), [scope.org, scope.project]);
  const p = project.data;

  async function toggleGeneral(packId: string, applied: boolean) {
    if (!p) return;
    const excluded = applied ? p.excluded_general_packs.filter((x) => x !== packId) : [...p.excluded_general_packs, packId];
    try {
      await api.patchProject(scope, { excluded_general_packs: excluded });
      project.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  if (project.error) return <main className="page"><p className="empty">{project.error}</p></main>;
  if (!p) return <main className="page"><p className="empty">Loading…</p></main>;

  return (
    <main className="page page-medium">
      <Breadcrumbs items={[{ label: "Organizations", href: "#/" }, { label: p.org_name, href: href({ page: "org", org: scope.org }) }, { label: p.name }]} />
      <section className="hero">
        <h1>{p.name}</h1>
        {p.description && <p className="muted">{p.description}</p>}
      </section>

      <div className="two-col wide-left">
        <div className="stack">
          <NewAnalysis scope={scope} health={health} />

          <section className="card">
            <h2 className="card-title">Analyses in this project</h2>
            {!analyses.data?.length ? <p className="muted">None yet.</p> : (
              <table className="table">
                <thead><tr><th>Started</th><th>Documents</th><th>Findings</th><th>Reviewed</th><th /></tr></thead>
                <tbody>
                  {analyses.data.map((a) => (
                    <tr key={a.id}>
                      <td>{new Date(a.created_at).toLocaleString()}</td>
                      <td className="truncate" title={a.documents.join(", ")}>{a.documents.length} · {a.documents.slice(0, 2).join(", ")}{a.documents.length > 2 ? "…" : ""}</td>
                      <td>
                        {a.summary ? (
                          <span className="badge-row">
                            {STATUS_ORDER.filter((s) => a.summary![s]).map((s) => <span key={s} className="badge-count"><StatusBadge status={s} /> {a.summary![s]}</span>)}
                          </span>
                        ) : <span className="muted">{a.status}</span>}
                      </td>
                      <td>{a.findings ? `${a.reviewed}/${a.findings}` : "–"}</td>
                      <td><a className="button small" href={href({ page: "analysis", ...scope, id: a.id })}>Open</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2 className="card-title">Default rules for this project ({p.rules.length})</h2>
            <p className="muted small">Pre-ticked for a new analysis; each analysis can use other packs, for example a suggested template.</p>
            {p.rules_problem && <p className="warn">{p.rules_problem}</p>}
            {p.rules.length > 0 && (
              <table className="table compact">
                <thead><tr><th>Rule</th><th>Checks</th><th>Severity</th><th>From</th></tr></thead>
                <tbody>
                  {p.rules.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.id}</code> {r.title}</td>
                      <td className="muted">{r.applies_to.map((k) => KIND_LABEL[k] ?? k).join(", ")} · {r.method === "code" ? "code" : "Decider"}</td>
                      <td><SeverityTag severity={r.severity} /></td>
                      <td>
                        <span className={`source source-${r.scope}`}>{r.scope === "project" ? "Project" : "Organization"} · {r.pack}</span>
                        {r.overrides && <span className="tag" title={`Replaces the rule with the same id from ${r.overrides}`}>overrides {r.overrides}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <h2 className="card-title">Project rule packs</h2>
            <p className="muted small">Only for {p.name}. A rule with the same id as a general rule replaces it here.</p>
            <PackList scope={scope} packs={p.project_packs} onChanged={project.reload} emptyText="No project-specific rules." />
          </section>
          <section className="card">
            <h2 className="card-title">General rule packs</h2>
            <p className="muted small">From {p.org_name}. <a href={href({ page: "org", org: scope.org })}>Manage</a></p>
            <PackList scope={{ org: scope.org, project: null }} packs={p.general_packs} onChanged={project.reload}
              toggle={{ excluded: p.excluded_general_packs, onToggle: toggleGeneral }} emptyText="The organization has no general packs." />
          </section>
        </div>
      </div>
    </main>
  );
}
