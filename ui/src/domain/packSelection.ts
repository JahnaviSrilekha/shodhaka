// Which rules an analysis will run with, from the packs ticked at upload (mirrors the server's compose:
// organization packs and templates first, project packs last, a project rule replaces one with the same id).
import type { Candidate, RuleInEffect } from "../api/types";

export function selectedRules(candidates: Candidate[], refs: string[]): RuleInEffect[] {
  const chosen = candidates.filter((c) => refs.includes(c.ref));
  const ordered = [...chosen.filter((c) => c.source !== "project"), ...chosen.filter((c) => c.source === "project")];
  const byId = new Map<string, RuleInEffect>();
  for (const c of ordered) {
    for (const r of c.rules) {
      const previous = byId.get(r.id);
      byId.set(r.id, {
        ...r,
        scope: c.source === "project" ? "project" : c.source === "template" ? "template" : "organization",
        pack: c.id,
        overrides: previous ? previous.pack : null,
      });
    }
  }
  return [...byId.values()];
}

/** Two ticked packs of the same layer must not define the same rule id (the server refuses it too). */
export function clashes(candidates: Candidate[], refs: string[]): string[] {
  const seen = new Map<string, string>();
  const out: string[] = [];
  for (const c of candidates.filter((x) => refs.includes(x.ref))) {
    const layer = c.source === "project" ? "project" : "general";
    for (const r of c.rules) {
      const key = `${layer}:${r.id}`;
      if (seen.has(key) && seen.get(key) !== c.id) out.push(`${r.id} is in both ${seen.get(key)} and ${c.id}`);
      seen.set(key, c.id);
    }
  }
  return out;
}

export const SOURCE_LABEL: Record<Candidate["source"], string> = {
  project: "Project pack",
  organization: "Organization pack",
  "organization-off": "Organization pack · off for this project",
  template: "Template · this analysis only",
};
