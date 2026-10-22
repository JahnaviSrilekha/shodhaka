import { describe, expect, it } from "vitest";
import type { RawPack } from "../api/types";
import { emptyPack, newRule, toForm, toRaw } from "./packForm";

const raw: RawPack = {
  pack: "acme", version: "1.0", title: "Acme", description: "rules",
  rules: [
    { id: "ARCH-01", title: "No shared DB", severity: "high", applies_to: ["adr"], requirement: "Each service owns its data.",
      decider: { topic: "data ownership", question: "How is data accessed?", scope: "document",
        options: { owns: { verdict: "compliant", description: "owns it" }, shares: { verdict: "gap", description: "shares it" } } },
      fix_hint: "Use APIs." },
    { id: "ARCH-03", title: "No secrets", severity: "high", applies_to: ["config"], requirement: "No literal secrets.",
      deterministic: { check: "secret_scan" } },
  ],
};

describe("pack form", () => {
  it("round-trips a raw pack without losing anything", () => {
    expect(toRaw(toForm(raw))).toEqual(raw);
  });

  it("drops empty optional fields and derives a question from the requirement", () => {
    const form = emptyPack();
    Object.assign(form, { pack: "p", title: "P" });
    Object.assign(form.rules[0], { id: "SEC-01", title: "t", requirement: "  Services   log no tokens. " });
    const out = toRaw(form);
    expect(out.description).toBeUndefined();
    expect(out.rules[0].fix_hint).toBeUndefined();
    expect(out.rules[0].decider?.question).toBe("Does what this text describes meet the requirement: Services log no tokens.");
    expect(Object.keys(out.rules[0].decider!.options)).toEqual(["meets-requirement", "breaks-requirement", "not-discussed"]);
  });

  it("numbers new rules after the pack's own prefix", () => {
    const form = toForm(raw);
    expect(newRule(form.rules).id).toBe("ARCH-04");
  });
});
