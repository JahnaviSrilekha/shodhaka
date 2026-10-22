import { useState, type FormEvent } from "react";
import { api } from "../../api/client";
import { useLoad } from "../../hooks/useLoad";
import { navigate } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";

/** Start: register an organisation or open one. */
export function OrgsPage() {
  const toast = useToast();
  const { data: orgs } = useLoad(() => api.orgs(), []);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  async function register(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const org = await api.createOrg(name, description);
      toast(`${org.name} registered`, "success");
      navigate({ page: "org", org: org.id });
    } catch (err) {
      toast((err as Error).message, "error");
      setBusy(false);
    }
  }

  return (
    <main className="page page-narrow">
      <section className="hero">
        <h1>Organizations</h1>
        <p className="muted">
          An organization keeps its general rule packs, which apply to every project. Each project adds its own rules
          and keeps its own documents and reviews, separate from every other project.
        </p>
      </section>

      {orgs && orgs.length > 0 && (
        <section className="card-grid">
          {orgs.map((o) => (
            <a key={o.id} className="tile" href={`#/o/${o.id}`}>
              <strong>{o.name}</strong>
              {o.description && <span className="muted">{o.description}</span>}
              <span className="tile-meta">{o.projects} project{o.projects === 1 ? "" : "s"} · {o.general_packs} general pack{o.general_packs === 1 ? "" : "s"}</span>
            </a>
          ))}
        </section>
      )}

      <form className="card" onSubmit={register}>
        <h2 className="card-title">Register an organization</h2>
        <div className="form-grid">
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme GmbH" required maxLength={120} />
          </label>
          <label className="field">
            <span>Description <small className="muted">(optional)</small></span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What the organization builds" />
          </label>
        </div>
        <div className="actions-row">
          <button className="button primary" disabled={!name.trim() || busy}>{busy ? "Registering…" : "Register"}</button>
        </div>
      </form>
    </main>
  );
}
