import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Health, Org, Project } from "../api/types";
import { navigate, type Route } from "../hooks/useHashRoute";
import { Icon } from "./Icon";

export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth({ decider: "down", error: "API not reachable", bedrock: false, default_threshold: 0.75 }));
    check();
    const t = window.setInterval(check, 15000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  return health;
}

/** Organisation and project switchers: the current scope is always visible and one click away. */
export function AppHeader({ health, route }: { health: Health | null; route: Route }) {
  const org = "org" in route ? route.org : null;
  const project = "project" in route ? route.project : null;
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => { api.orgs().then(setOrgs).catch(() => setOrgs([])); }, [route.page, org]);
  useEffect(() => {
    if (!org) { setProjects([]); return; }
    api.org(org).then((o) => setProjects(o.projects)).catch(() => setProjects([]));
  }, [org, project, route.page]);

  return (
    <header className="app-header">
      <div className="header-left">
        <a href="#/" className="brand">
          <span className="brand-mark"><Icon name="check" size={14} /></span>
          <span className="brand-name">Shodhaka</span>
        </a>
        {orgs.length > 0 && (
          <div className="switchers">
            <label className="switcher">
              <span className="visually-hidden">Organization</span>
              <select value={org ?? ""} onChange={(e) => e.target.value ? navigate({ page: "org", org: e.target.value }) : navigate({ page: "home" })}>
                <option value="">All organizations</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </label>
            {org && (
              <label className="switcher">
                <span className="visually-hidden">Project</span>
                <select value={project ?? ""} onChange={(e) => e.target.value ? navigate({ page: "project", org, project: e.target.value }) : navigate({ page: "org", org })}>
                  <option value="">{projects.length ? "All projects" : "No projects yet"}</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
      </div>
      <div className="header-status">
        <span className="privacy"><Icon name="shield" size={14} /> Full documents stay on this machine</span>
        <span className={`dot-status ${health?.decider === "up" ? "up" : "down"}`} title={health?.error ?? health?.checkpoint ?? ""}>
          Decider {health ? (health.decider === "up" ? "ready" : "offline") : "…"}
        </span>
      </div>
    </header>
  );
}
