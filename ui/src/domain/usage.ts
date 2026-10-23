import type { UsageTotals } from "../api/types";

/** Small amounts stay readable: $0.00042 rather than $0.00. */
export function usd(value: number | null | undefined): string {
  const v = value ?? 0;
  if (v === 0) return "$0";
  if (v < 0.01) return `$${v.toPrecision(2)}`;
  return `$${v.toFixed(2)}`;
}

/** Project totals: the sum over every analysis that has usage recorded. */
export function sumUsage(items: (UsageTotals | null | undefined)[]) {
  const present = items.filter((u): u is UsageTotals => !!u);
  return {
    analyses: present.length,
    deciderRequests: present.reduce((s, u) => s + u.decider.requests, 0),
    bedrockCalls: present.reduce((s, u) => s + u.bedrock.calls, 0),
    guardrailUnits: present.reduce((s, u) => s + u.guardrail.text_units, 0),
    guardrailInterventions: present.reduce((s, u) => s + u.guardrail.interventions, 0),
    usd: present.reduce((s, u) => s + u.usd, 0),
  };
}
