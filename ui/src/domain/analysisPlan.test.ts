import { describe, expect, it } from "vitest";
import type { RuleInEffect } from "../api/types";
import { modeExplanation, plan } from "./analysisPlan";

const rule = (id: string, method: "decider" | "code", scope: "section" | "document" | null, applies = ["adr"]): RuleInEffect => ({
  id, title: id, severity: "high", applies_to: applies, method, applies_per: scope, scope: "organization", pack: "p", overrides: null,
});

const rules = [rule("ARCH-01", "decider", "section"), rule("ARCH-04", "decider", "document"), rule("ARCH-03", "code", null, ["config"])];

describe("analysis plan", () => {
  it("asks how documents relate only when there are two or more design documents", () => {
    expect(plan(["a.md", "app.yml"], rules).needsChoice).toBe(false);
    const p = plan(["a.md", "b.pdf", "app.yml", "x.Dockerfile"], rules);
    expect(p.needsChoice).toBe(true);
    expect(p.designDocs).toEqual(["a.md", "b.pdf"]);
    expect(p.codeFiles).toEqual(["app.yml", "x.Dockerfile"]);
  });

  it("explains presence and prohibition rules for a design set", () => {
    const p = plan(["a.md", "b.md"], rules);
    const text = modeExplanation(p, "design-set").join(" ");
    expect(text).toContain("Met if any document has it: ARCH-04");
    expect(text).toContain("A gap if any document breaks it");
    expect(text).toContain("ARCH-01");
    expect(modeExplanation(p, "per-document")[0]).toContain("on its own");
  });
});
