// Pure review rules, shared by every component and unit-tested on their own.
import { DESIGN_SET, type Finding, type Review, type Status, type Verdict } from "../api/types";

export const STATUS_ORDER: Status[] = ["gap", "needs_review", "covered", "not_applicable"];

export const STATUS_LABEL: Record<Status, string> = {
  gap: "Gap",
  needs_review: "Needs review",
  covered: "Covered",
  not_applicable: "Not applicable",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  gap: "Gap",
  compliant: "Compliant",
  not_applicable: "Not applicable",
};

/** What the tool claimed, in reviewer terms. needs_review makes no claim. */
export const TOOL_VERDICT: Record<Status, Verdict | null> = {
  gap: "gap",
  covered: "compliant",
  not_applicable: "not_applicable",
  needs_review: null,
};

export type ReviewState = "pending" | "approved" | "rejected" | "resolved" | "stale";

/** stale = the document was edited and re-checked after the review, so the decision must be made again. */
export function reviewState(finding: Finding, review?: Review): ReviewState {
  if (!review) return "pending";
  if (review.stale || review.tool_status !== finding.status) return "stale";
  return review.decision;
}

export interface ReviewAction {
  key: string;
  label: string;
  decision: Review["decision"];
  verdict?: Verdict;
  primary: boolean;
}

/** Approve agrees with the tool; reject replaces its verdict; needs_review is resolved by choosing. */
export function actionsFor(finding: Finding): ReviewAction[] {
  const tool = TOOL_VERDICT[finding.status];
  const verdicts: Verdict[] = ["gap", "compliant", "not_applicable"];
  if (tool === null) {
    return verdicts.map((v) => ({ key: v, label: `It's ${VERDICT_LABEL[v].toLowerCase()}`, decision: "resolved", verdict: v, primary: false }));
  }
  return [
    { key: "approve", label: `Approve: ${VERDICT_LABEL[tool].toLowerCase()}`, decision: "approved", primary: true },
    ...verdicts
      .filter((v) => v !== tool)
      .map((v) => ({ key: v, label: `Reject: ${VERDICT_LABEL[v].toLowerCase()}`, decision: "rejected" as const, verdict: v, primary: false })),
  ];
}

const SEVERITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** Review order: what needs a person most comes first. */
export function sortForReview(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) ||
      a.document.localeCompare(b.document) ||
      a.rule_id.localeCompare(b.rule_id),
  );
}

export interface FindingFilter {
  statuses: Set<Status>;
  document: string | null;
  onlyOpen: boolean;
  query: string;
}

export function applyFilter(findings: Finding[], reviews: Record<string, Review>, filter: FindingFilter): Finding[] {
  const q = filter.query.trim().toLowerCase();
  return sortForReview(findings).filter((f) => {
    if (filter.statuses.size && !filter.statuses.has(f.status)) return false;
    if (filter.document && f.document !== filter.document) return false;
    const state = reviewState(f, reviews[f.id]);
    if (filter.onlyOpen && state !== "pending" && state !== "stale") return false;
    if (q && !`${f.rule_id} ${f.rule_title} ${f.document} ${f.evidence.map((e) => e.text).join(" ")}`.toLowerCase().includes(q))
      return false;
    return true;
  });
}

export function progress(findings: Finding[], reviews: Record<string, Review>) {
  const done = findings.filter((f) => {
    const s = reviewState(f, reviews[f.id]);
    return s !== "pending" && s !== "stale";
  }).length;
  return { done, total: findings.length, percent: findings.length ? Math.round((done / findings.length) * 100) : 0 };
}

/** Lines where a fix for this finding should go: the end of its evidence section. */
export function insertionLine(text: string, sections: { heading: string; start_line: number }[], heading?: string): number {
  const lines = text.split("\n");
  const index = sections.findIndex((s) => s.heading === heading);
  if (index === -1) return lines.length;
  const next = sections[index + 1];
  let end = next ? next.start_line - 1 : lines.length; // 1-based line before the next heading
  while (end > sections[index].start_line && lines[end - 1]?.trim() === "") end -= 1;
  return end;
}

export const isDesignSet = (f: Finding) => f.document === DESIGN_SET;
export const docLabel = (doc: string) => (doc === DESIGN_SET ? "All design documents" : doc);

/** Does this finding concern the given document? (design-set findings concern every document in the set) */
export function touches(f: Finding, path: string): boolean {
  return f.document === path || (isDesignSet(f) && (f.documents ?? []).includes(path));
}

/** Where a fix most likely belongs: the evidence section; else (no quote, e.g. a whole-document rule
 * that was never confirmed) the section Decider found most on-topic. Only a starting point for the cursor.
 * For a design-set finding, pass the open document: only its sections are considered. */
export function targetHeading(finding: Finding, path?: string): string | undefined {
  const inSet = isDesignSet(finding);
  const quote = finding.evidence.find((e) => e.role !== "meets" && (!inSet || e.document === path));
  if (quote?.section) return quote.section;
  const onTopic = finding.sections
    .filter((s) => (s.verdict === "gap" || s.verdict === "compliant") && (!inSet || s.section.startsWith(`${path}#`)))
    .sort((a, b) => b.confidence - a.confidence);
  const heading = onTopic[0]?.heading;
  return inSet && heading ? heading.split(" › ").slice(1).join(" › ") : heading;
}

/** Character offset of the end of a 1-based line. */
export function lineEndOffset(text: string, line: number): number {
  return text.split("\n").slice(0, Math.max(0, line)).join("\n").length;
}

/** Insert the reviewed fix where the reviewer's cursor is; returns the new text and the cursor after it. */
export function insertAt(text: string, offset: number, finding: Finding, fix: string): { text: string; cursor: number } {
  const at = Math.max(0, Math.min(offset, text.length));
  const block = `\n\n> **${finding.rule_id} fix (reviewed):** ${fix.trim().replace(/\n+/g, " ")}\n`;
  return { text: text.slice(0, at) + block + text.slice(at), cursor: at + block.length };
}

export function insertFix(text: string, sections: { heading: string; start_line: number }[], finding: Finding, fix: string): string {
  const lines = text.split("\n");
  const at = insertionLine(text, sections, targetHeading(finding));
  const block = ["", `> **${finding.rule_id} fix (reviewed):** ${fix.trim().replace(/\n+/g, " ")}`];
  lines.splice(at, 0, ...block);
  return lines.join("\n");
}
