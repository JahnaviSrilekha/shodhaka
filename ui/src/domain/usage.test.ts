import { describe, expect, it } from "vitest";
import { sumUsage, usd } from "./usage";

const u = (requests: number, calls: number, units: number, cost: number) => ({
  decider: { requests, questions: 0, input_tokens: 0, usd: 0 },
  bedrock: { calls, blocked_by_egress_guard: 0, input_tokens: 0, output_tokens: 0, usd: cost },
  guardrail: { text_units: units, interventions: 0, usd: 0 },
  usd: cost, runs: 1,
});

describe("usage", () => {
  it("formats tiny and normal amounts", () => {
    expect(usd(0)).toBe("$0");
    expect(usd(0.00042)).toBe("$0.00042");
    expect(usd(1.234)).toBe("$1.23");
  });
  it("sums a project and skips analyses without usage", () => {
    const total = sumUsage([u(10, 2, 4, 0.001), null, u(5, 0, 0, 0)]);
    expect(total).toMatchObject({ analyses: 2, deciderRequests: 15, bedrockCalls: 2, guardrailUnits: 4 });
    expect(total.usd).toBeCloseTo(0.001);
  });
});
