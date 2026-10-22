"""The gap-analysis engine: one engine for every rule pack.

Who decides what:
  * code      — deterministic checks (secrets, health endpoint, pinned images)
  * Decider   — typed choice per (rule, section), confidence-gated
  * human     — every finding stays `pending` until a person accepts or rejects it

Nothing is ever marked "passed". The best a rule can get is `covered`, which still needs sign-off.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from . import checks
from .compiler import compliance_question, evidence_question, relevance_question, section_questions, section_state
from .decider import Decider
from .documents import Document, Section
from .retrieval import Ranker, shortlist
from .rulepack import Rule, RulePack

DEFAULT_THRESHOLD = 0.9

# status values
GAP = "gap"                # confident gap
NEEDS_REVIEW = "needs_review"  # low confidence either way: escalate to Bedrock / human
COVERED = "covered"        # confident evidence the rule is met (still needs sign-off)
NOT_APPLICABLE = "not_applicable"


@dataclass
class SectionDecision:
    section: str
    heading: str
    option: str
    verdict: str
    confidence: float


@dataclass
class Finding:
    id: str
    rule_id: str
    rule_title: str
    severity: str
    document: str
    status: str
    decided_by: str  # code | decider
    confidence: float
    evidence: list[dict] = field(default_factory=list)  # {"section"?, "line"?, "text"}
    sections: list[SectionDecision] = field(default_factory=list)
    reason: str = ""
    scope: str = "section"
    suggested_fix: str = ""
    fix_source: str = ""  # bedrock | rule-hint | ""
    human_decision: str = "pending"  # pending | accepted | rejected | edited
    documents: list[str] = field(default_factory=list)  # design-set findings: the documents judged together

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = round(self.confidence, 3)
        for s in data["sections"]:
            s["confidence"] = round(s["confidence"], 3)
        return data


def _finding_id(rule_id: str, document: str) -> str:
    return f"{rule_id}:{document}"


def _code_finding(rule: Rule, doc: Document) -> Finding:
    result = checks.CHECKS[rule.deterministic](doc, rule.params)
    status = {"gap": GAP, "compliant": COVERED, "not_applicable": NOT_APPLICABLE}[result.verdict]
    return Finding(
        id=_finding_id(rule.id, doc.path),
        rule_id=rule.id,
        rule_title=rule.title,
        severity=rule.severity,
        document=doc.path,
        status=status,
        decided_by="code",
        confidence=1.0,
        evidence=result.evidence,
        reason=result.note,
    )


def gate(sections: list[dict], threshold: float, scope: str = "section") -> tuple[str, float, str]:
    """The confidence gate: per-section answers -> (status, confidence, reason).
    Shared by analyze() and by calibrate's offline re-scoring, so both always agree.

    scope "section": any confident gap makes the rule a gap.
    scope "document": one section that confidently meets the rule covers the whole document;
    sections that only fail to mention it do not count as gaps (the conflict is noted)."""
    gaps = [s for s in sections if s["verdict"] == "gap"]
    covered = [s for s in sections if s["verdict"] == "compliant"]
    confident_gaps = [s for s in gaps if s["confidence"] >= threshold]
    confident_cover = [s for s in covered if s["confidence"] >= threshold]

    def top(items):
        return max(items, key=lambda s: s["confidence"])

    if scope == "document" and confident_cover:
        best = top(confident_cover)
        note = f"; '{top(gaps)['heading']}' does not mention it" if gaps else ""
        return COVERED, best["confidence"], f"covered by section '{best['heading']}'{note}"
    if confident_gaps:
        best = top(confident_gaps)
        return GAP, best["confidence"], f"gap in section '{best['heading']}'"
    if gaps:
        best = top(gaps)
        return NEEDS_REVIEW, best["confidence"], (
            f"possible gap in section '{best['heading']}' below the {threshold:.2f} confidence threshold")
    if confident_cover:
        best = top(confident_cover)
        return COVERED, best["confidence"], f"covered by section '{best['heading']}'"
    if covered:
        best = top(covered)
        return NEEDS_REVIEW, best["confidence"], (
            f"possibly covered by section '{best['heading']}', below the {threshold:.2f} confidence threshold")
    return NOT_APPLICABLE, max((s["confidence"] for s in sections), default=1.0), "no section discusses this rule"


def _aggregate(rule: Rule, doc: Document, decisions: list[SectionDecision], threshold: float) -> Finding:
    status, conf, reason = gate([asdict(s) for s in decisions], threshold, rule.decider.scope)
    return Finding(
        id=_finding_id(rule.id, doc.path),
        rule_id=rule.id,
        rule_title=rule.title,
        severity=rule.severity,
        document=doc.path,
        status=status,
        decided_by="decider",
        confidence=conf,
        sections=decisions,
        reason=reason,
        scope=rule.decider.scope,
    )


DESIGN_SET = "(design set)"  # the `document` of findings that judge several design documents together
MODES = ("per-document", "design-set")


def _attach_evidence(finding: Finding, rule: Rule, doc: Document, decider: Decider) -> None:
    """For a gap (or possible gap), ask Decider which sentence is the evidence."""
    candidates = [s for s in finding.sections if s.verdict == "gap"]
    if not candidates:
        return
    best = max(candidates, key=lambda s: s.confidence)
    section = next(sec for sec in doc.sections if sec.id == best.section)
    options = rule.decider.options
    claim = next((o.description for o in options if o.name == best.option),
                 next(o.description for o in options if o.verdict == "gap"))
    built = evidence_question(section, claim)
    if built is None:
        finding.evidence = [{"section": section.heading, "text": section.text.strip()}]
        return
    question, keyed = built
    answer = decider.ask(section_state(doc, section), {"evidence": question})["evidence"]
    finding.evidence = [{"section": section.heading, "text": keyed[answer.option], "confidence": round(answer.confidence, 3)}]


def _design_set_finding(rule: Rule, parts: list[tuple[Document, list[SectionDecision]]],
                        threshold: float, decider: Decider) -> Finding:
    """One finding per rule for the whole set: the sections of every document vote together.
    Section ids and headings carry their document ("adr-1.md#s3", "adr-1.md › Data")."""
    merged_sections, decisions, origin = [], [], {}
    for doc, answers in parts:
        for sec in doc.sections:
            key = f"{doc.path}#{sec.id}"
            merged_sections.append(Section(key, f"{doc.path} › {sec.heading}", sec.text, sec.start_line))
            origin[key] = (doc.path, sec.heading)
        for a in answers:
            decisions.append(SectionDecision(f"{doc.path}#{a.section}", f"{doc.path} › {a.heading}",
                                             a.option, a.verdict, a.confidence))
    merged = Document(DESIGN_SET, "adr", "", "Design split across documents", merged_sections)
    finding = _aggregate(rule, merged, decisions, threshold)
    if finding.status in (GAP, NEEDS_REVIEW):
        _attach_evidence(finding, rule, merged, decider)
    for e in finding.evidence:
        key = next((k for k, (path, heading) in origin.items() if f"{path} › {heading}" == e.get("section")), None)
        if key:
            e["document"], e["section"] = origin[key]
            e["role"] = "breaks"
    # show where the rule is met too, so a reviewer sees both sides of a conflict
    covering = sorted((d for d in decisions if d.verdict == "compliant"), key=lambda d: -d.confidence)
    if covering and (finding.status != COVERED or not finding.evidence):
        best = covering[0]
        path, heading = origin[best.section]
        text = next(s.text for s in merged_sections if s.id == best.section)
        finding.evidence.append({"document": path, "section": heading, "text": text.strip()[:600],
                                 "confidence": round(best.confidence, 3), "role": "meets"})
    finding.documents = sorted({doc.path for doc, _ in parts})
    return finding


STRATEGIES = ("two-stage", "choice")
RELEVANT = 0.5  # stage-1 probability above which a section counts as on topic
METADATA_HEADINGS = {"preamble", "status"}


def _is_metadata(section) -> bool:
    """Title/status/owner lines carry no design content; asking about them only adds noise."""
    return section.heading.lower() in METADATA_HEADINGS and len(section.text) < 300


def _option_for(rule: Rule, verdict: str) -> str:
    return next((o.name for o in rule.decider.options if o.verdict == verdict), verdict)


def _choice_decisions(doc: Document, rules: list[Rule], decider: Decider) -> dict[str, list[SectionDecision]]:
    """One 3-way choice per (rule, section): compliant / gap / not discussed."""
    per_rule: dict[str, list[SectionDecision]] = {r.id: [] for r in rules}
    questions = section_questions(rules)
    for section in doc.sections:
        answers = decider.ask(section_state(doc, section), questions)
        for rule in rules:
            answer = answers[rule.id]
            per_rule[rule.id].append(SectionDecision(section.id, section.heading, answer.option,
                                                     rule.decider.verdict_of(answer.option), answer.confidence))
    return per_rule


NOT_CHECKED = "not-checked-retrieval"


def _two_stage_decisions(doc: Document, rules: list[Rule], decider: Decider,
                         picks: dict[str, set[int]] | None = None) -> dict[str, list[SectionDecision]]:
    """Stage 1: one yes/no per rule — is the section on topic? (all rules in one request)
    Stage 2: one yes/no per on-topic rule — does it meet the requirement? (one request)
    Yes/no answers are sharper than a 3-way choice, and off-topic sections no longer vote.
    `picks` (from retrieval) limits which sections each rule is checked against; skipped pairs are
    recorded as not applicable with option 'not-checked-retrieval', never as compliant."""
    per_rule: dict[str, list[SectionDecision]] = {r.id: [] for r in rules}
    for index, section in enumerate(doc.sections):
        state = section_state(doc, section)
        candidates = [r for r in rules if picks is None or index in picks[r.id]]
        for rule in rules:
            if rule not in candidates:
                per_rule[rule.id].append(SectionDecision(section.id, section.heading, NOT_CHECKED, "not_applicable", 1.0))
        if not candidates:
            continue
        relevance = decider.ask(state, {r.id: relevance_question(r) for r in candidates})
        on_topic = [r for r in candidates if relevance[r.id].p_true >= RELEVANT]
        for rule in candidates:
            if rule not in on_topic:
                per_rule[rule.id].append(SectionDecision(section.id, section.heading, _option_for(rule, "not_applicable"),
                                                         "not_applicable", 1 - relevance[rule.id].p_true))
        if not on_topic:
            continue
        compliance = decider.ask(state, {r.id: compliance_question(r) for r in on_topic})
        for rule in on_topic:
            answer = compliance[rule.id]
            verdict = "compliant" if answer.option == "true" else "gap"
            per_rule[rule.id].append(SectionDecision(section.id, section.heading, _option_for(rule, verdict),
                                                     verdict, answer.confidence))
    return per_rule


def analyze(pack: RulePack, documents: list[Document], decider: Decider,
            threshold: float = DEFAULT_THRESHOLD, strategy: str = "two-stage",
            ranker: Ranker | None = None, top_k: int = 3,
            progress: Callable[[int, int, str], None] | None = None,
            mode: str = "per-document") -> dict[str, Any]:
    """`ranker` (optional, see retrieval.py): check each rule only against its top_k sections.
    `progress(done, total, path)` is called before each document (the UI shows it).

    mode "per-document": every design document must meet every rule on its own.
    mode "design-set": the design documents are one design split across files. Each section is
    still asked separately, then the answers of all documents are combined per rule with the same
    gate: a rule with scope "document" (something that must be present, e.g. a correlation id) is
    met if any section of any document meets it; a rule with scope "section" (something that must
    never happen, e.g. a shared database) is a gap if any section anywhere breaks it.
    Config files and Dockerfiles are always checked file by file."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    if ranker is not None and strategy != "two-stage":
        raise ValueError("retrieval works with the two-stage strategy")
    findings: list[Finding] = []
    pairs_total = pairs_checked = 0
    design_set: dict[str, list[tuple[Document, list[SectionDecision]]]] = {}  # rule id -> per document
    for index, doc in enumerate(documents):
        if progress is not None:
            progress(index, len(documents), doc.path)
        rules = pack.rules_for(doc.kind)
        for rule in (r for r in rules if r.deterministic):
            findings.append(_code_finding(rule, doc))

        decider_rules = [r for r in rules if r.decider]
        if not decider_rules:
            continue
        content = Document(doc.path, doc.kind, doc.text, doc.title,
                           [sec for sec in doc.sections if not _is_metadata(sec)] or doc.sections)
        pairs_total += len(content.sections) * len(decider_rules)
        if strategy == "choice":
            per_rule = _choice_decisions(content, decider_rules, decider)
            pairs_checked += len(content.sections) * len(decider_rules)
        else:
            picks = (shortlist(ranker, decider_rules, [f"{s.heading}. {s.text}" for s in content.sections], top_k)
                     if ranker is not None else None)
            pairs_checked += (sum(len(v) for v in picks.values()) if picks is not None
                              else len(content.sections) * len(decider_rules))
            per_rule = _two_stage_decisions(content, decider_rules, decider, picks)
        if mode == "design-set" and doc.kind == "adr":
            for rule in decider_rules:
                design_set.setdefault(rule.id, []).append((content, per_rule[rule.id]))
            continue
        for rule in decider_rules:
            finding = _aggregate(rule, content, per_rule[rule.id], threshold)
            if finding.status in (GAP, NEEDS_REVIEW):
                _attach_evidence(finding, rule, content, decider)
            findings.append(finding)

    for rule_id, parts in design_set.items():
        findings.append(_design_set_finding(pack.rule(rule_id), parts, threshold, decider))

    summary = {status: sum(1 for f in findings if f.status == status)
               for status in (GAP, NEEDS_REVIEW, COVERED, NOT_APPLICABLE)}
    return {
        "run_id": uuid.uuid4().hex[:12],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pack": {"id": pack.pack, "version": pack.version, "title": pack.title},
        "threshold": threshold,
        "strategy": strategy,
        "retrieval": {"method": ranker.name if ranker else "none", "top_k": top_k if ranker else None,
                      "pairs_checked": pairs_checked, "pairs_total": pairs_total},
        "documents": [d.path for d in documents],
        "mode": mode,
        "design_set": sorted({d.path for parts in design_set.values() for d, _ in parts}),
        "summary": summary,
        "decider": getattr(getattr(decider, "stats", None), "as_dict", lambda: {})(),
        "egress": {"bedrock_calls": 0, "bytes_sent": 0, "log": []},
        "findings": [f.to_dict() for f in findings],
    }
