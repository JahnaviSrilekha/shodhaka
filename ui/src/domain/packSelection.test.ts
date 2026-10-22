import { describe, expect, it } from "vitest";
import type { Candidate } from "../api/types";
import { clashes, selectedRules } from "./packSelection";

const cand = (ref: string, source: Candidate["source"], ids: string[], severity = "high"): Candidate => ({
  ref, source, in_effect: source !== "template", id: ref.split(":")[1], title: ref, version: "1", description: "",
  rules: ids.map((id) => ({ id, title: id, severity, applies_to: ["adr"], method: "decider", applies_per: "section" })),
});

describe("pack selection", () => {
  it("layers ticked packs like the server: project rules override", () => {
    const c = [cand("org:arch", "organization", ["ARCH-01", "ARCH-07"]), cand("project:pay", "project", ["ARCH-07", "PAY-01"], "low"),
      cand("template:dora", "template", ["DORA-01"])];
    const rules = selectedRules(c, ["org:arch", "project:pay", "template:dora"]);
    expect(rules.map((r) => r.id).sort()).toEqual(["ARCH-01", "ARCH-07", "DORA-01", "PAY-01"]);
    const a7 = rules.find((r) => r.id === "ARCH-07")!;
    expect([a7.scope, a7.overrides, a7.severity]).toEqual(["project", "arch", "low"]);
    expect(rules.find((r) => r.id === "DORA-01")!.scope).toBe("template");
    expect(selectedRules(c, ["template:dora"]).map((r) => r.id)).toEqual(["DORA-01"]);
  });

  it("reports the same rule id in two general packs", () => {
    const c = [cand("org:a", "organization", ["X-01"]), cand("template:b", "template", ["X-01"])];
    expect(clashes(c, ["org:a", "template:b"])).toEqual(["X-01 is in both a and b"]);
    expect(clashes(c, ["org:a"])).toEqual([]);
  });
});
