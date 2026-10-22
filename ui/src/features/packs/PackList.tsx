import { useEffect, useRef, useState } from "react";
import { api, packProblems, type PackScope } from "../../api/client";
import type { PackSummary } from "../../api/types";
import { Icon } from "../../components/Icon";
import { href } from "../../hooks/useHashRoute";
import { useToast } from "../../hooks/useToast";

interface Props {
  scope: PackScope;
  packs: PackSummary[];
  onChanged: () => void;
  /** general packs seen from a project: show an on/off switch instead of edit links */
  toggle?: { excluded: string[]; onToggle: (packId: string, applied: boolean) => void };
  emptyText: string;
}

/** Rule packs of one level (organization or project): list, add from file / template / editor. */
export function PackList({ scope, packs, onChanged, toggle, emptyText }: Props) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [templates, setTemplates] = useState<PackSummary[]>([]);
  useEffect(() => { if (!toggle) api.templates().then(setTemplates).catch(() => {}); }, [toggle]);

  async function add(input: Parameters<typeof api.createPack>[1], label: string) {
    try {
      const pack = await api.createPack(scope, input);
      toast(`Added ${pack.title}`, "success");
      onChanged();
    } catch (e) {
      const problems = packProblems(e);
      toast(problems.length ? `${label} is not a valid rule pack: ${problems.slice(0, 2).join("; ")}` : (e as Error).message, "error");
    }
  }

  async function remove(pack: PackSummary) {
    if (!window.confirm(`Delete the rule pack “${pack.title}”? Earlier analyses keep the rules they ran with.`)) return;
    try {
      await api.deletePack(scope, pack.id);
      onChanged();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="pack-list">
      {packs.length === 0 && <p className="muted">{emptyText}</p>}
      {packs.map((p) => {
        const applied = toggle ? !toggle.excluded.includes(p.id) : true;
        return (
          <div key={p.id} className={`pack-row ${applied ? "" : "pack-off"}`}>
            <div className="pack-main">
              <strong>{p.title}</strong>
              <span className="muted small"><code>{p.id}</code> · v{p.version} · {p.rules.length} rule{p.rules.length === 1 ? "" : "s"}</span>
              {p.error && <span className="warn small">{p.error}</span>}
            </div>
            {toggle ? (
              <label className="switch" title={applied ? "Applies to this project" : "Switched off for this project"}>
                <input type="checkbox" checked={applied} onChange={(e) => toggle.onToggle(p.id, e.target.checked)} />
                <span>{applied ? "Applied" : "Off"}</span>
              </label>
            ) : (
              <div className="row-actions">
                <a className="button small" href={href({ page: "pack", org: scope.org, project: scope.project, pack: p.id })}><Icon name="edit" /> Edit</a>
                <button className="icon-button" aria-label={`Delete ${p.title}`} onClick={() => remove(p)}><Icon name="x" /></button>
              </div>
            )}
          </div>
        );
      })}
      {!toggle && (
        <div className="add-row">
          <a className="button small primary" href={href({ page: "pack", org: scope.org, project: scope.project, pack: "new" })}>+ New pack</a>
          <button className="button small" onClick={() => file.current?.click()}><Icon name="upload" /> Upload YAML</button>
          {templates.length > 0 && (
            <select className="small-select" value="" aria-label="Add from template"
              onChange={(e) => e.target.value && add({ template: e.target.value }, "The template")}>
              <option value="">From template…</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
            </select>
          )}
          <input ref={file} type="file" accept=".yaml,.yml" hidden data-testid="pack-file"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) add({ yaml: await f.text() }, f.name);
            }} />
        </div>
      )}
    </div>
  );
}
