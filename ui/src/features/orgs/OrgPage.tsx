import { useState, type FormEvent } from "react";
import { api } from "../../api/client";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { DeleteButton } from "../../components/DeleteButton";
import { useLoad } from "../../hooks/useLoad";
import { href, navigate } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";
import { PackList } from "../packs/PackList";

export function OrgPage({ org }: { org: string }) {
  const toast = useToast();
  const { data, error, reload } = useLoad(() => api.org(org), [org]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function createProject(e: FormEvent) {
    e.preventDefault();
    try {
      const project = await api.createProject(org, name, description);
      navigate({ page: "project", org, project: project.id });
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  if (error) return <main className="page"><p className="empty">{error}</p></main>;
  if (!data) return <main className="page"><p className="empty">Loading…</p></main>;

  return (
    <main className="page page-medium">
      <Breadcrumbs items={[{ label: "Organizations", href: "#/" }, { label: data.name }]} />
      <section className="hero hero-row">
        <div>
          <h1>{data.name}</h1>
          {data.description && <p className="muted">{data.description}</p>}
        </div>
        <DeleteButton what="organization"
          detail={`Delete ${data.name} with its ${data.projects.length} project${data.projects.length === 1 ? "" : "s"}, rule packs, documents and reviews? It is moved to the workspace trash.`}
          onDelete={async () => {
            try {
              await api.deleteOrg(org);
              toast(`${data.name} deleted`, "success");
              navigate({ page: "home" });
            } catch (err) {
              toast((err as Error).message, "error");
            }
          }} />
      </section>

      <div className="two-col">
        <section className="card">
          <h2 className="card-title">Projects</h2>
          {data.projects.length === 0 && <p className="muted">No projects yet. Each project has its own documents, reviews and extra rules.</p>}
          <div className="tile-list">
            {data.projects.map((p) => (
              <a key={p.id} className="tile" href={href({ page: "project", org, project: p.id })}>
                <strong>{p.name}</strong>
                {p.description && <span className="muted">{p.description}</span>}
                <span className="tile-meta">
                  {p.analyses} analys{p.analyses === 1 ? "is" : "es"} · {p.project_packs} project pack{p.project_packs === 1 ? "" : "s"}
                  {p.excluded_general_packs.length > 0 && ` · ${p.excluded_general_packs.length} general pack${p.excluded_general_packs.length === 1 ? "" : "s"} off`}
                </span>
              </a>
            ))}
          </div>
          <form className="inline-form" onSubmit={createProject}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New project name" aria-label="New project name" required maxLength={120} />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" aria-label="Project description" />
            <button className="button primary" disabled={!name.trim()}>Create project</button>
          </form>
        </section>

        <section className="card">
          <h2 className="card-title">General rule packs</h2>
          <p className="muted small">Apply to every project in {data.name}. A project can switch a pack off or replace single rules with its own.</p>
          <PackList scope={{ org, project: null }} packs={data.general_packs} onChanged={reload}
            emptyText="No general rule packs yet: start from a template, upload a YAML file or write one." />
        </section>
      </div>
    </main>
  );
}
