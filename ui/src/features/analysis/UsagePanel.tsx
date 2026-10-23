import type { Usage } from "../../api/types";
import { usd } from "../../domain/usage";

/** What this analysis called and what it cost, including re-checks. Prices are list-price estimates. */
export function UsagePanel({ usage, bedrockOn }: { usage: Usage; bedrockOn: boolean }) {
  const t = usage.total;
  const [priceIn, priceOut] = usage.prices.model_per_1m_tokens;
  return (
    <section className="card usage-card" aria-labelledby="usage-title">
      <h2 className="card-title" id="usage-title">
        Calls and cost <span className="muted small">· {t.runs} run{t.runs === 1 ? "" : "s"} · estimate</span>
      </h2>
      <div className="usage-grid">
        <div className="usage-item">
          <span className="muted small">Strands Decider 2B · local</span>
          <strong>{t.decider.requests.toLocaleString()} requests</strong>
          <span className="muted small">{t.decider.questions.toLocaleString()} questions{t.decider.input_tokens ? ` · ${t.decider.input_tokens.toLocaleString()} tokens` : ""}</span>
          <span className="usage-cost">{usd(0)}</span>
        </div>
        <div className="usage-item">
          <span className="muted small">Amazon Bedrock{t.bedrock.model ? ` · ${t.bedrock.model}` : ""}</span>
          {bedrockOn || t.bedrock.calls ? (
            <>
              <strong>{t.bedrock.calls} calls</strong>
              <span className="muted small">
                {t.bedrock.input_tokens.toLocaleString()} in / {t.bedrock.output_tokens.toLocaleString()} out tokens
                {t.bedrock.blocked_by_egress_guard ? ` · ${t.bedrock.blocked_by_egress_guard} blocked by the egress guard` : ""}
              </span>
            </>
          ) : <strong>off</strong>}
          <span className="usage-cost">{usd(t.bedrock.usd)}</span>
        </div>
        <div className="usage-item">
          <span className="muted small">Bedrock Guardrail{t.guardrail.id ? ` · ${t.guardrail.id}` : ""}</span>
          {t.guardrail.id ? (
            <>
              <strong>{t.guardrail.text_units} text units</strong>
              <span className="muted small">{t.guardrail.interventions} intervention{t.guardrail.interventions === 1 ? "" : "s"}</span>
            </>
          ) : <strong>off</strong>}
          <span className="usage-cost">{usd(t.guardrail.usd)}</span>
        </div>
        <div className="usage-item usage-total">
          <span className="muted small">Total</span>
          <strong className="usage-cost">{usd(t.usd)}</strong>
          <span className="muted small">
            Nova at ${priceIn}/${priceOut} per 1M tokens · guardrail ${usage.prices.guardrail_per_1000_text_units.toFixed(2)} per 1,000 text units
          </span>
        </div>
      </div>
    </section>
  );
}
