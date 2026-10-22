// Mirrors the JSON written by src/gapanalyzer (engine.py report, api.py analysis + reviews).
export type Status = "gap" | "needs_review" | "covered" | "not_applicable";
export type Verdict = "gap" | "compliant" | "not_applicable";
export type Decision = "approved" | "rejected" | "resolved";
export type RunStatus = "queued" | "cleaning" | "running" | "done" | "failed";
export type AnalysisMode = "per-document" | "design-set";
/** `document` of findings that judge several design documents together */
export const DESIGN_SET = "(design set)";

export interface Evidence {
  document?: string; // design-set findings: which document the quote is from
  role?: "breaks" | "meets";
  section?: string;
  line?: number;
  text: string;
  confidence?: number;
}

export interface SectionAnswer {
  section: string;
  heading: string;
  option: string;
  verdict: string;
  confidence: number;
}

export interface Finding {
  id: string;
  rule_id: string;
  rule_title: string;
  severity: "high" | "medium" | "low" | string;
  document: string;
  status: Status;
  decided_by: "code" | "decider";
  confidence: number;
  evidence: Evidence[];
  sections: SectionAnswer[];
  reason: string;
  scope: "section" | "document";
  suggested_fix: string;
  fix_source: string;
  rule_source?: RuleSource | null;
  documents?: string[]; // design-set findings: the documents judged together
}

export interface RuleSource {
  scope: "organization" | "project" | "template";
  pack: string;
  overrides: string | null;
}

export interface Report {
  run_id: string;
  created_at: string;
  pack: { id: string; version: string; title: string };
  threshold: number;
  strategy: string;
  documents: string[];
  mode?: AnalysisMode;
  design_set?: string[];
  summary: Record<Status, number>;
  decider: { calls?: number; latency_ms_p50?: number; latency_ms_p95?: number };
  egress: { bedrock_calls: number; bytes_sent: number };
  findings: Finding[];
  rechecks?: { document: string; at: string }[];
}

export interface Review {
  finding_id: string;
  rule_id: string;
  document: string;
  decision: Decision;
  verdict: Verdict;
  tool_status: Status;
  note: string;
  fix: string | null;
  reviewed_at: string;
  /** set by the server when the document was edited and re-checked after this decision */
  stale?: boolean;
}

export interface AnalysisMeta {
  id: string;
  org: string;
  project: string;
  pack: string;
  packs: string[];
  threshold: number;
  bedrock: boolean;
  mode?: AnalysisMode;
  notes?: string[];
  documents: string[];
  skipped: { file: string; reason: string }[];
  status: RunStatus;
  error: string | null;
  progress: { done: number; total: number; current: string | null };
  edited: string[];
  created_at: string;
  finished_at: string | null;
}

/** Content removed from the analysed copy right after upload (sanitize.py). The value itself is never kept. */
export interface Removal {
  document: string;
  type: "secret" | "personal" | "instruction" | "unsafe";
  label: string;
  line: number;
  preview: string;
  by: "pattern" | "Decider";
  confidence?: number;
  on_edit?: boolean;
}

export interface Analysis extends AnalysisMeta {
  report: Report | null;
  removals?: Removal[];
  reviews: Record<string, Review>;
}

export interface AnalysisListItem extends AnalysisMeta {
  summary: Record<Status, number> | null;
  findings: number;
  reviewed: number;
}

export interface RuleSummary {
  id: string;
  title: string;
  severity: string;
  applies_to: string[];
  method: "decider" | "code";
  applies_per?: "section" | "document" | null; // Decider rules: gap anywhere (section) or met anywhere (document)
}

export interface PackSummary {
  id: string;
  title: string;
  version: string;
  description: string;
  rules: RuleSummary[];
  error?: string;
  applied?: boolean; // general packs, seen from a project
}

export interface Org {
  id: string;
  name: string;
  description: string;
  created_at: string;
  projects?: number;
  general_packs?: number;
}

export interface Project {
  id: string;
  org: string;
  name: string;
  description: string;
  excluded_general_packs: string[];
  created_at: string;
  analyses?: number;
  project_packs?: number;
}

export interface OrgDetail extends Omit<Org, "projects" | "general_packs"> {
  projects: Project[];
  general_packs: PackSummary[];
}

export interface RuleInEffect extends RuleSummary, Omit<RuleSource, "scope"> {
  scope: RuleSource["scope"] | "template";
}

export interface ProjectDetail extends Omit<Project, "project_packs"> {
  org_name: string;
  general_packs: PackSummary[];
  project_packs: PackSummary[];
  rules: RuleInEffect[];
  packs_in_effect: string[];
  rules_problem: string | null;
}

// Raw rule pack, as in specs/contracts/rulepack.schema.json
export interface RawOption { verdict: "compliant" | "gap" | "not_applicable"; description: string }
export interface RawRule {
  id: string;
  title: string;
  severity: "low" | "medium" | "high";
  applies_to: string[];
  requirement: string;
  fix_hint?: string;
  decider?: { topic?: string; question: string; scope?: "section" | "document"; options: Record<string, RawOption> };
  deterministic?: { check: string; params?: Record<string, unknown> };
}
export interface RawPack { pack: string; version: string; title: string; description?: string; rules: RawRule[] }

export interface PackDocument { pack: RawPack; yaml: string; checks: string[] }
export interface ValidateResult { valid: boolean; problems: string[]; pack: RawPack | null; yaml: string | null; checks?: string[] }
export interface PackInput { yaml?: string; pack?: RawPack; template?: string }

export interface Health {
  decider: "up" | "down";
  checkpoint?: string;
  error?: string;
  bedrock: boolean;
  default_threshold: number;
}

export interface DocumentText {
  path: string;
  kind: "adr" | "config" | "dockerfile" | null;
  text: string;
  original_format: string;
  edited: boolean;
  sections: { id: string; heading: string; start_line: number }[];
}

export interface ReviewInput {
  decision: Decision;
  verdict?: Verdict;
  note?: string;
  fix?: string | null;
}

/** A pack a project could use for one analysis; ref = "project:<id>" | "org:<id>" | "template:<id>". */
export interface Candidate extends PackSummary {
  ref: string;
  source: "project" | "organization" | "organization-off" | "template";
  in_effect: boolean;
}

export interface Recommendation {
  documents: { document: string; kind: string; pick: string | null; confidence: number; by: string }[];
  packs: { ref: string; probability: number; picked_by: string[] }[];
  recommended: string[];
  candidates: Candidate[];
}
