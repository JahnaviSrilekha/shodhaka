"""Draft fixes for gaps with Amazon Bedrock, behind two Decider-backed guards.

  * EgressGuard (before_model_call): nothing reaches Bedrock while it still contains an
    original identifier the redactor replaced, a sensitive pattern, or — per Decider —
    identifying details. Every allowed call is logged with its byte count.
  * FixGuard (before_tool_call on submit_fix): Decider checks the proposed fix actually
    resolves the gap; if not, the model gets Guide feedback and tries again (max 2 times).

Without Bedrock (offline mode) the rule's own fix_hint is used and nothing leaves the machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import decider as d
from .decider import Decider
from .redact import Redactor
from .rulepack import Rule, RulePack

DEFAULT_MODEL = "eu.amazon.nova-lite-v1:0"
DEFAULT_REGION = "eu-central-1"

SYSTEM_PROMPT = (
    "You are a senior software architect. You receive one architecture-rule gap with a short, "
    "redacted excerpt as evidence. Placeholders such as [HOST_1] stand for redacted values; keep "
    "them as they are. Write a concrete fix in 2 to 4 sentences that makes the design meet the "
    "rule, then call submit_fix exactly once with that fix. Do not invent details beyond the evidence."
)


def _render(messages: list[dict]) -> str:
    parts = []
    for message in messages:
        for block in message.get("content", []):
            if isinstance(block, dict):
                if "text" in block:
                    parts.append(block["text"])
                elif "toolUse" in block:
                    parts.append(json.dumps(block["toolUse"].get("input", {})))
                elif "toolResult" in block:
                    parts.append(json.dumps(block["toolResult"].get("content", [])))
    return "\n".join(parts)


@dataclass
class EgressLog:
    calls: int = 0
    bytes_sent: int = 0
    blocked: int = 0
    entries: list[dict] = field(default_factory=list)


def _interventions():
    # Imported lazily so the engine and tests run without strands-agents installed.
    from strands.interventions import Deny, Guide, InterventionHandler, Proceed

    class EgressGuard(InterventionHandler):
        name = "egress-guard"

        def __init__(self, redactor: Redactor, decider: Decider | None, log: EgressLog, finding_id: str) -> None:
            self.redactor, self.decider, self.log, self.finding_id = redactor, decider, log, finding_id

        def before_model_call(self, event, **kwargs):
            text = _render(event.agent.messages)
            leaks = self.redactor.leaks(text)
            if not leaks and self.decider is not None:
                answer = self.decider.ask(text, {"identifying": d.noul(
                    "Does this text still contain identifying details such as real hostnames, IP addresses, "
                    "credentials, e-mail addresses or person names?",
                    true="a real identifying value is present in clear text",
                    false="only generic terms and bracketed placeholders like [HOST_1] appear",
                )})["identifying"]
                if answer.p_true >= 0.8:
                    leaks = [f"decider:identifying p={answer.p_true:.2f}"]
            if leaks:
                self.log.blocked += 1
                self.log.entries.append({"finding": self.finding_id, "allowed": False, "reason": "unredacted content", "bytes": 0})
                return Deny(reason="Blocked by egress guard: the prompt still contains identifying details.")
            size = len(text.encode("utf-8"))
            self.log.calls += 1
            self.log.bytes_sent += size
            self.log.entries.append({"finding": self.finding_id, "allowed": True, "bytes": size, "text": text})
            return Proceed()

    class FixGuard(InterventionHandler):
        name = "fix-guard"

        def __init__(self, decider: Decider | None, rule: Rule, evidence: str) -> None:
            self.decider, self.rule, self.evidence, self.attempts = decider, rule, evidence, 0

        def before_tool_call(self, event, **kwargs):
            if event.tool_use["name"] != "submit_fix" or self.decider is None:
                return Proceed()
            fix = (event.tool_use.get("input") or {}).get("fix", "")
            state = (f"Rule: {self.rule.title}\nRequirement: {self.rule.requirement}\n"
                     f"Evidence of the gap: {self.evidence}\nProposed fix: {fix}")
            answer = self.decider.ask(state, {"resolves": d.noul(
                "Does the proposed fix resolve the gap so that the requirement is met?",
                true="the fix directly removes the problem described in the evidence",
                false="the fix is vague, off-topic, or leaves the problem in place",
            )})["resolves"]
            self.attempts += 1
            if answer.p_true < 0.5 and self.attempts <= 2:
                return Guide(feedback=(
                    f"The fix does not yet resolve the gap for rule {self.rule.id}: {self.rule.requirement} "
                    "Make it concrete and address the evidence directly, then call submit_fix again."))
            return Proceed()

    return EgressGuard, FixGuard


class FixWriter:
    def __init__(self, decider: Decider | None, model_id: str = DEFAULT_MODEL, region: str = DEFAULT_REGION) -> None:
        self.decider, self.model_id, self.region = decider, model_id, region
        self.redactor = Redactor()
        self.log = EgressLog()

    def draft(self, rule: Rule, finding: dict[str, Any]) -> str:
        from strands import Agent, tool
        from strands.models import BedrockModel

        EgressGuard, FixGuard = _interventions()
        evidence = " ".join(e.get("text", "") for e in finding.get("evidence", []))[:800]
        redacted = self.redactor.redact(evidence)
        submitted: dict[str, str] = {}

        @tool
        def submit_fix(fix: str) -> str:
            """Record the proposed fix for this gap.

            Args:
                fix: The concrete fix, 2 to 4 sentences.
            """
            submitted["fix"] = fix
            return "Fix recorded."

        agent = Agent(
            model=BedrockModel(model_id=self.model_id, region_name=self.region, max_tokens=400),
            tools=[submit_fix],
            interventions=[EgressGuard(self.redactor, self.decider, self.log, finding["id"]),
                           FixGuard(self.decider, rule, redacted)],
            system_prompt=SYSTEM_PROMPT,
            callback_handler=None,
        )
        prompt = (f"Rule {rule.id}: {rule.title}\nRequirement: {rule.requirement}\n"
                  f"Problem found: {finding.get('reason', '')}\nEvidence (redacted): {redacted}\n"
                  f"Hint from the rule owner: {rule.fix_hint}")
        result = agent(prompt)
        return self.redactor.restore(submitted.get("fix") or str(result)).strip()


def add_fixes(report: dict[str, Any], pack: RulePack, writer: FixWriter | None) -> dict[str, Any]:
    """Fill suggested_fix for every gap or needs_review finding."""
    for finding in report["findings"]:
        if finding["status"] not in ("gap", "needs_review"):
            continue
        rule = pack.rule(finding["rule_id"])
        if writer is None:
            finding["suggested_fix"], finding["fix_source"] = rule.fix_hint, "rule-hint"
            continue
        try:
            finding["suggested_fix"], finding["fix_source"] = writer.draft(rule, finding), "bedrock"
        except Exception as exc:  # noqa: BLE001 — a Bedrock failure must not lose the finding
            finding["suggested_fix"], finding["fix_source"] = rule.fix_hint, f"rule-hint (bedrock failed: {type(exc).__name__})"
    if writer is not None:
        report["egress"] = {"bedrock_calls": writer.log.calls, "bytes_sent": writer.log.bytes_sent,
                            "blocked": writer.log.blocked, "log": writer.log.entries}
    return report
