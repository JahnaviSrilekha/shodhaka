// The editor works on a form-friendly shape (options as a list, empty strings instead of missing
// keys) and converts to and from the raw rule pack the server validates.
import type { RawOption, RawPack, RawRule } from "../api/types";

export type Kind = "adr" | "config" | "dockerfile";
export const KINDS: { value: Kind; label: string }[] = [
  { value: "adr", label: "Design docs & ADRs" },
  { value: "config", label: "Config files" },
  { value: "dockerfile", label: "Dockerfiles" },
];
export const CHECK_LABEL: Record<string, string> = {
  secret_scan: "No literal secrets (config)",
  health_endpoint: "Health endpoint exposed (Spring config)",
  pinned_base_image: "Pinned base images (Dockerfile)",
};
export const CHECK_KIND: Record<string, Kind> = { secret_scan: "config", health_endpoint: "config", pinned_base_image: "dockerfile" };

export interface FormOption { name: string; verdict: RawOption["verdict"]; description: string }
export interface FormRule {
  id: string;
  title: string;
  severity: RawRule["severity"];
  applies_to: string[];
  requirement: string;
  fix_hint: string;
  method: "decider" | "code";
  topic: string;
  question: string;
  scope: "section" | "document";
  options: FormOption[];
  check: string;
}
export interface FormPack { pack: string; version: string; title: string; description: string; rules: FormRule[] }

export const standardOptions = (): FormOption[] => [
  { name: "meets-requirement", verdict: "compliant", description: "the text describes a design that meets the requirement" },
  { name: "breaks-requirement", verdict: "gap", description: "the text describes a design that breaks the requirement" },
  { name: "not-discussed", verdict: "not_applicable", description: "the text does not discuss this topic" },
];

export function newRule(existing: FormRule[], prefix = "RULE"): FormRule {
  const used = new Set(existing.map((r) => r.id));
  const base = existing[0]?.id.split("-")[0] || prefix;
  let n = existing.length + 1;
  while (used.has(`${base}-${String(n).padStart(2, "0")}`)) n += 1;
  return {
    id: `${base}-${String(n).padStart(2, "0")}`, title: "", severity: "medium", applies_to: ["adr"], requirement: "",
    fix_hint: "", method: "decider", topic: "", question: "", scope: "section", options: standardOptions(), check: "secret_scan",
  };
}

export const emptyPack = (): FormPack => ({ pack: "", version: "1.0", title: "", description: "", rules: [newRule([])] });

export function toForm(raw: RawPack): FormPack {
  return {
    pack: raw.pack ?? "", version: String(raw.version ?? ""), title: raw.title ?? "", description: raw.description ?? "",
    rules: (raw.rules ?? []).map((r) => ({
      id: r.id ?? "", title: r.title ?? "", severity: r.severity ?? "medium", applies_to: r.applies_to ?? [],
      requirement: r.requirement ?? "", fix_hint: r.fix_hint ?? "",
      method: r.deterministic ? "code" : "decider",
      topic: r.decider?.topic ?? "", question: r.decider?.question ?? "", scope: r.decider?.scope ?? "section",
      options: r.decider ? Object.entries(r.decider.options ?? {}).map(([name, o]) => ({ name, ...o })) : standardOptions(),
      check: r.deterministic?.check ?? "secret_scan",
    })),
  };
}

const clean = (s: string) => s.trim().replace(/\s+/g, " ");

export function toRaw(form: FormPack): RawPack {
  const raw: RawPack = { pack: form.pack.trim(), version: form.version.trim(), title: form.title.trim(), rules: [] };
  if (form.description.trim()) raw.description = clean(form.description);
  raw.rules = form.rules.map((r) => {
    const rule: RawRule = {
      id: r.id.trim(), title: r.title.trim(), severity: r.severity, applies_to: r.applies_to, requirement: clean(r.requirement),
    };
    if (r.method === "code") {
      rule.deterministic = { check: r.check };
    } else {
      rule.decider = {
        ...(r.topic.trim() ? { topic: clean(r.topic) } : {}),
        // a question is required by the schema; derive one from the requirement when left empty
        question: clean(r.question) || `Does what this text describes meet the requirement: ${clean(r.requirement)}`,
        ...(r.scope === "document" ? { scope: "document" as const } : {}),
        options: Object.fromEntries(r.options.map((o) => [o.name.trim(), { verdict: o.verdict, description: clean(o.description) }])),
      };
    }
    if (r.fix_hint.trim()) rule.fix_hint = clean(r.fix_hint);
    return rule;
  });
  return raw;
}
