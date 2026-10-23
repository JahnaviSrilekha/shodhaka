"""Calls and estimated cost of an analysis, kept per analysis in usage.json.

Decider runs locally, so it has no per-request price. Bedrock is charged per token, the Bedrock
Guardrail per text unit (up to 1,000 characters) for each paid policy. All prices are on-demand list
prices and only an estimate; set your own with environment variables:

    SHODHAKA_PRICE_IN / SHODHAKA_PRICE_OUT   USD per 1M input / output tokens of the fix model
    SHODHAKA_GUARDRAIL_PRICE                 USD per 1,000 text units, all paid policies together
                                             (content filters 0.15 + denied topics 0.15 + PII 0.10;
                                             word filters and custom regex are free)
"""

from __future__ import annotations

import math
import os
from typing import Any

# USD per 1M input and output tokens, on-demand
MODEL_PRICES = {"nova-micro": (0.035, 0.14), "nova-lite": (0.06, 0.24), "nova-pro": (0.80, 3.20)}
DEFAULT_GUARDRAIL_PRICE = 0.40


def model_price(model_id: str | None) -> tuple[float, float]:
    if os.environ.get("SHODHAKA_PRICE_IN") and os.environ.get("SHODHAKA_PRICE_OUT"):
        return float(os.environ["SHODHAKA_PRICE_IN"]), float(os.environ["SHODHAKA_PRICE_OUT"])
    for key, price in MODEL_PRICES.items():
        if model_id and key in model_id:
            return price
    return MODEL_PRICES["nova-lite"]


def guardrail_price() -> float:
    return float(os.environ.get("SHODHAKA_GUARDRAIL_PRICE", DEFAULT_GUARDRAIL_PRICE))


def text_units(chars: int) -> int:
    return math.ceil(chars / 1000) if chars > 0 else 0


def run_usage(decider_stats: dict[str, Any], egress: dict[str, Any] | None, model_id: str | None) -> dict[str, Any]:
    """One run (analysis or re-check): what was called and what it cost."""
    egress = egress or {}
    price_in, price_out = model_price(model_id)
    tokens_in, tokens_out = egress.get("input_tokens", 0), egress.get("output_tokens", 0)
    bedrock_usd = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    units = egress.get("guardrail_text_units", 0) if egress.get("guardrail") else 0
    guardrail_usd = units / 1000 * guardrail_price()
    return {
        "decider": {"requests": decider_stats.get("calls", 0), "questions": decider_stats.get("questions", 0),
                    "input_tokens": decider_stats.get("input_tokens", 0), "usd": 0.0},
        "bedrock": {"model": model_id if egress.get("bedrock_calls") else None, "calls": egress.get("bedrock_calls", 0),
                    "blocked_by_egress_guard": egress.get("blocked", 0),
                    "input_tokens": tokens_in, "output_tokens": tokens_out, "usd": round(bedrock_usd, 6)},
        "guardrail": {"id": egress.get("guardrail"), "text_units": units,
                      "interventions": egress.get("guardrail_interventions", 0), "usd": round(guardrail_usd, 6)},
        "usd": round(bedrock_usd + guardrail_usd, 6),
    }


def add_run(usage: dict[str, Any] | None, run: dict[str, Any], kind: str, at: str) -> dict[str, Any]:
    """Append a run and keep running totals, so re-checks add to the analysis' cost."""
    usage = usage or {"runs": [], "total": None}
    runs = usage["runs"] + [{"kind": kind, "at": at, **run}]
    total: dict[str, Any] = {}
    for part in ("decider", "bedrock", "guardrail"):
        total[part] = {}
        for r in runs:
            for key, value in r[part].items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    total[part][key] = round(total[part].get(key, 0) + value, 6)
                elif value is not None:
                    total[part][key] = value
    total["usd"] = round(sum(r["usd"] for r in runs), 6)
    total["runs"] = len(runs)
    return {"runs": runs, "total": total,
            "prices": {"model_per_1m_tokens": model_price(total["bedrock"].get("model")),
                       "guardrail_per_1000_text_units": guardrail_price()}}
