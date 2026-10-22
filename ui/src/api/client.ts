// The only module that talks HTTP. Components and hooks call these functions, never fetch().
// Everything below an organisation is addressed through a Scope, so one project's data can
// only be reached with that project's ids.
import type {
  AnalysisMode, Analysis, Candidate, Recommendation, AnalysisListItem, AnalysisMeta, DocumentText, Health, Org, OrgDetail, PackDocument, PackInput,
  PackSummary, Project, ProjectDetail, Review, ReviewInput, ValidateResult,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export interface Scope { org: string; project: string }
export interface PackScope { org: string; project: string | null }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = response.statusText;
    }
    const message =
      typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join("; ")
      : detail && typeof detail === "object" && "message" in detail ? String((detail as { message: unknown }).message)
      : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, detail);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const enc = (documentPath: string) => documentPath.split("/").map(encodeURIComponent).join("/");
const projectBase = (s: Scope) => `/orgs/${s.org}/projects/${s.project}`;
const packBase = (s: PackScope) => (s.project ? `${projectBase(s as Scope)}/packs` : `/orgs/${s.org}/packs`);

/** Problems listed by the server for an invalid rule pack (422), else []. */
export function packProblems(error: unknown): string[] {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object" && "problems" in error.detail) {
    return (error.detail as { problems: string[] }).problems;
  }
  return [];
}

export const api = {
  health: () => request<Health>("/health"),
  templates: () => request<PackSummary[]>("/templates"),
  validatePack: (input: PackInput) => request<ValidateResult>("/packs/validate", json("POST", input)),

  orgs: () => request<Org[]>("/orgs"),
  createOrg: (name: string, description: string) => request<Org>("/orgs", json("POST", { name, description })),
  org: (org: string) => request<OrgDetail>(`/orgs/${org}`),
  createProject: (org: string, name: string, description: string) =>
    request<Project>(`/orgs/${org}/projects`, json("POST", { name, description })),
  project: (s: Scope) => request<ProjectDetail>(projectBase(s)),
  patchProject: (s: Scope, patch: Partial<Pick<Project, "name" | "description" | "excluded_general_packs">>) =>
    request<ProjectDetail>(projectBase(s), json("PATCH", patch)),

  pack: (s: PackScope, id: string) => request<PackDocument>(`${packBase(s)}/${id}`),
  createPack: (s: PackScope, input: PackInput) => request<PackSummary>(packBase(s), json("POST", input)),
  updatePack: (s: PackScope, id: string, input: PackInput) => request<PackSummary>(`${packBase(s)}/${id}`, json("PUT", input)),
  deletePack: (s: PackScope, id: string) => request<void>(`${packBase(s)}/${id}`, { method: "DELETE" }),

  analyses: (s: Scope) => request<AnalysisListItem[]>(`${projectBase(s)}/analyses`),
  analysis: (s: Scope, id: string) => request<Analysis>(`${projectBase(s)}/analyses/${id}`),
  candidates: (s: Scope) => request<Candidate[]>(`${projectBase(s)}/candidates`),
  /** Read-only: Decider suggests packs from the start of each document; nothing is stored. */
  recommend(s: Scope, files: File[]) {
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    return request<Recommendation>(`${projectBase(s)}/recommend`, { method: "POST", body: form });
  },
  createAnalysis(s: Scope, files: File[], threshold: number, useBedrock: boolean, mode: AnalysisMode = "per-document", packs: string[] = []) {
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    form.append("threshold", String(threshold));
    form.append("use_bedrock", String(useBedrock));
    form.append("mode", mode);
    form.append("packs", packs.join(","));
    return request<AnalysisMeta>(`${projectBase(s)}/analyses`, { method: "POST", body: form });
  },

  saveReview: (s: Scope, id: string, findingId: string, input: ReviewInput) =>
    request<Review>(`${projectBase(s)}/analyses/${id}/reviews/${enc(findingId)}`, json("PUT", input)),
  clearReview: (s: Scope, id: string, findingId: string) =>
    request<void>(`${projectBase(s)}/analyses/${id}/reviews/${enc(findingId)}`, { method: "DELETE" }),

  document: (s: Scope, id: string, path: string) => request<DocumentText>(`${projectBase(s)}/analyses/${id}/documents/${enc(path)}`),
  saveDocument: (s: Scope, id: string, path: string, text: string) =>
    request<DocumentText>(`${projectBase(s)}/analyses/${id}/documents/${enc(path)}`, json("PUT", { text })),
  recheck: (s: Scope, id: string, path: string) =>
    request<AnalysisMeta>(`${projectBase(s)}/analyses/${id}/documents/${enc(path)}/recheck`, { method: "POST" }),

  exportUrl: {
    expected: (s: Scope, id: string) => `/api${projectBase(s)}/analyses/${id}/export/expected.json`,
    report: (s: Scope, id: string) => `/api${projectBase(s)}/analyses/${id}/export/report.json`,
    rules: (s: Scope, id: string) => `/api${projectBase(s)}/analyses/${id}/export/rules.yaml`,
    document: (s: Scope, id: string, path: string) => `/api${projectBase(s)}/analyses/${id}/export/document/${enc(path)}`,
  },
};
