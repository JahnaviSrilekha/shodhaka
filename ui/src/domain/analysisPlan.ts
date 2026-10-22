// What an analysis will do, in words, shown to the person before anything runs.
import type { AnalysisMode, RuleInEffect } from "../api/types";

const DESIGN_EXT = [".md", ".markdown", ".pdf", ".docx"];
export const isDesignDoc = (name: string) => DESIGN_EXT.some((ext) => name.toLowerCase().endsWith(ext));

export interface Plan {
  designDocs: string[];
  codeFiles: string[];
  needsChoice: boolean;          // 2+ design documents: the person must say how they relate
  presence: RuleInEffect[];      // Decider rules with scope "document": something must appear
  prohibition: RuleInEffect[];   // Decider rules with scope "section": something must never happen
  codeRules: RuleInEffect[];
}

export function plan(fileNames: string[], rules: RuleInEffect[]): Plan {
  const designDocs = fileNames.filter(isDesignDoc);
  const decider = rules.filter((r) => r.method === "decider" && r.applies_to.includes("adr"));
  return {
    designDocs,
    codeFiles: fileNames.filter((n) => !isDesignDoc(n)),
    needsChoice: designDocs.length >= 2,
    presence: decider.filter((r) => r.applies_per === "document"),
    prohibition: decider.filter((r) => r.applies_per !== "document"),
    codeRules: rules.filter((r) => r.method === "code"),
  };
}

export const ids = (rules: RuleInEffect[]) => rules.map((r) => r.id).join(", ");

/** One sentence per rule group explaining how the chosen mode treats it. */
export function modeExplanation(p: Plan, mode: AnalysisMode): string[] {
  if (mode === "per-document") {
    return [`Each of the ${p.designDocs.length} documents must meet every rule on its own; you get one finding per rule per document.`];
  }
  const lines = [`The ${p.designDocs.length} documents are read as one design or policy set; you get one finding per rule for the whole set.`];
  if (p.presence.length) lines.push(`Met if any document has it: ${ids(p.presence)}.`);
  if (p.prohibition.length) lines.push(`A gap if any document breaks it (the quote and a section that meets it are both shown): ${ids(p.prohibition)}.`);
  return lines;
}
