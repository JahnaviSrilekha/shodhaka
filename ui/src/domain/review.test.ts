import { describe, expect, it } from "vitest";
import type { Finding, Review } from "../api/types";
import { actionsFor, applyFilter, insertAt, insertFix, progress, reviewState, sortForReview, targetHeading } from "./review";
import { parseRoute, href } from "../hooks/useHashRoute";

const finding = (over: Partial<Finding>): Finding => ({
  id: "ARCH-02:adr.md", rule_id: "ARCH-02", rule_title: "Reliable events", severity: "high", document: "adr.md",
  status: "gap", decided_by: "decider", confidence: 0.9, evidence: [{ section: "Publishing", text: "sends after commit" }],
  sections: [], reason: "", scope: "section", suggested_fix: "Use an outbox.", fix_source: "rule-hint", ...over,
});
const review = (over: Partial<Review>): Review => ({
  finding_id: "ARCH-02:adr.md", rule_id: "ARCH-02", document: "adr.md", decision: "approved", verdict: "gap",
  tool_status: "gap", note: "", fix: null, reviewed_at: "2026-10-18T10:00:00Z", ...over,
});

describe("review rules", () => {
  it("offers approve plus two rejections when the tool made a call", () => {
    const actions = actionsFor(finding({ status: "covered" }));
    expect(actions.map((a) => [a.decision, a.verdict])).toEqual([
      ["approved", undefined], ["rejected", "gap"], ["rejected", "not_applicable"],
    ]);
  });

  it("makes the person choose when the Decider was unsure", () => {
    const actions = actionsFor(finding({ status: "needs_review" }));
    expect(actions.every((a) => a.decision === "resolved" && !a.primary)).toBe(true);
    expect(actions).toHaveLength(3);
  });

  it("marks a review stale after a re-check changed the tool's answer", () => {
    expect(reviewState(finding({ status: "covered" }), review({ tool_status: "gap" }))).toBe("stale");
    expect(reviewState(finding({}), review({}))).toBe("approved");
    expect(reviewState(finding({}), undefined)).toBe("pending");
  });

  it("puts gaps and high severity first, and counts stale reviews as open", () => {
    const list = [finding({ id: "b", status: "covered" }), finding({ id: "a", status: "gap", severity: "low" }),
      finding({ id: "c", status: "gap", severity: "high" })];
    expect(sortForReview(list).map((f) => f.id)).toEqual(["c", "a", "b"]);
    const reviews = { c: review({ finding_id: "c" }), b: review({ finding_id: "b", tool_status: "gap" }) };
    expect(progress(list, reviews)).toEqual({ done: 1, total: 3, percent: 33 });
    const open = applyFilter(list, reviews, { statuses: new Set(), document: null, onlyOpen: true, query: "" });
    expect(open.map((f) => f.id)).toEqual(["a", "b"]);
  });

  it("inserts a fix at the end of the evidence section, before the next heading", () => {
    const text = "# ADR\n\n## Publishing\nSends after commit.\n\n## Tax\nCalls the tax API.";
    const sections = [{ heading: "Publishing", start_line: 3 }, { heading: "Tax", start_line: 6 }];
    const out = insertFix(text, sections, finding({}), "Use an outbox.");
    expect(out.split("\n")).toEqual([
      "# ADR", "", "## Publishing", "Sends after commit.", "", "> **ARCH-02 fix (reviewed):** Use an outbox.", "", "## Tax", "Calls the tax API.",
    ]);
  });
});

describe("fix placement", () => {
  it("inserts at the reviewer's cursor", () => {
    const text = "## A\nfirst\n\n## B\nsecond";
    const at = text.indexOf("second") + "second".length;
    const out = insertAt(text, at, finding({ rule_id: "ARCH-04" }), "Pass traceparent on every call.");
    expect(out.text.endsWith("second\n\n> **ARCH-04 fix (reviewed):** Pass traceparent on every call.\n")).toBe(true);
    expect(out.cursor).toBe(out.text.length);
  });

  it("starts at the evidence section, else the section Decider found most on-topic", () => {
    expect(targetHeading(finding({}))).toBe("Publishing");
    const sections = [
      { section: "s1", heading: "Preamble", option: "", verdict: "compliant", confidence: 0.56 },
      { section: "s3", heading: "Database calls", option: "", verdict: "compliant", confidence: 0.7 },
      { section: "s2", heading: "Build", option: "", verdict: "not_applicable", confidence: 0.95 },
    ];
    expect(targetHeading(finding({ evidence: [], sections, scope: "document" }))).toBe("Database calls");
    expect(targetHeading(finding({ evidence: [], sections: [] }))).toBeUndefined();
  });
});

describe("routes", () => {
  it("round-trips document paths with slashes", () => {
    const route = { page: "document" as const, org: "111111111111", project: "222222222222", id: "abcdef123456",
      path: "config/app.yml", finding: "ARCH-03:config/app.yml" };
    expect(parseRoute(href(route))).toEqual(route);
    const pack = { page: "pack" as const, org: "111111111111", project: null, pack: "security-baseline" };
    expect(parseRoute(href(pack))).toEqual(pack);
    expect(parseRoute("#/a/abcdef123456")).toEqual({ page: "home" }); // old unscoped links do not leak into a project
    expect(parseRoute("#/nope")).toEqual({ page: "home" });
  });
});
