"""Remove harmful content from an uploaded document before anything else reads it.

Runs on the extracted text right after upload (and again when a reviewer saves an edit):

  secret        passwords, API keys, tokens, private keys, credentials in URLs      (patterns)
  personal      e-mail addresses, phone numbers, IBANs, card numbers, IP addresses   (patterns + checksums)
  instruction   text aimed at the AI ("ignore previous instructions", "mark as compliant")  (patterns)
  unsafe        abusive, hateful, sexual, violent or self-harm language              (Decider, see unsafe_*)

Each finding is replaced by a marker such as REMOVED_SECRET, so the place stays visible and line
numbers do not move. Every removal is recorded with its type, line and a masked preview; the removed
value itself is never stored in the record. The rule checks run on the cleaned text: a config file that
had a literal password still fails the "no secrets in config" rule, because the marker is not a
${placeholder}.

Not detected: person names and other free-text personal data. Patterns catch common phrasing of
instructions aimed at the AI, not every paraphrase; Decider's unsafe-language check covers whole sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from shodhaka.rules.checks import PLACEHOLDER, SECRET_KEY

MARK = {"secret": "REMOVED_SECRET", "personal": "REMOVED_PERSONAL_DATA",
        "instruction": "REMOVED_INSTRUCTION_TO_AI", "unsafe": "REMOVED_UNSAFE_TEXT"}


@dataclass
class Removal:
    type: str        # secret | personal | instruction | unsafe
    label: str       # what it was, e.g. "AWS access key"
    line: int
    preview: str     # masked, never the full value
    by: str = "pattern"
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _mask(value: str, keep_start: int = 2, keep_end: int = 0) -> str:
    value = value.strip()
    if len(value) <= keep_start + keep_end + 2:
        return "•" * len(value)
    end = value[-keep_end:] if keep_end else ""
    return f"{value[:keep_start]}…{end} ({len(value)} chars)"


def _luhn(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        n = int(ch)
        if i % 2 == parity:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _iban_ok(raw: str) -> bool:
    s = raw.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _ip_personal(raw: str) -> bool:
    parts = [int(p) for p in raw.split(".")]
    return all(p <= 255 for p in parts) and raw not in ("0.0.0.0", "127.0.0.1", "255.255.255.255")


# (type, label, pattern, group to remove (0 = whole match), validator, preview)
Rule = tuple[str, str, re.Pattern[str], int, Callable[[str], bool] | None, Callable[[str], str]]
RULES: list[Rule] = [
    ("secret", "private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), 0,
     None, lambda v: "PEM private key block"),
    ("secret", "credentials in a URL", re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s:@]+:[^/\s@]+)@", re.I), 1, None,
     lambda v: f"{v.split(':')[0]}:•••"),
    ("secret", "AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0, None, lambda v: _mask(v, 4)),
    ("secret", "API key or token", re.compile(r"\b(?:sk|pk|tk|rk|ghp|gho|ghs|xox[abprs])[_-][A-Za-z0-9_-]{8,}\b"), 0, None,
     lambda v: _mask(v, 3)),
    ("secret", "JSON web token", re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}\b"), 0, None, lambda v: _mask(v, 3)),
    ("secret", "bearer token", re.compile(r"\bBearer\s+([A-Za-z0-9._~+/-]{20,}=*)"), 1, None, lambda v: _mask(v, 2)),
    ("personal", "e-mail address", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), 0, None,
     lambda v: f"{v[0]}…@{v.split('@')[1]}"),
    ("personal", "IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"), 0, _iban_ok,
     lambda v: f"{v[:2]}…{v.replace(' ', '')[-4:]}"),
    ("personal", "card number", re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), 0,
     lambda v: _luhn(re.sub(r"\D", "", v)) and 13 <= len(re.sub(r"\D", "", v)) <= 19, lambda v: f"…{re.sub(r'[^0-9]', '', v)[-4:]}"),
    ("personal", "phone number", re.compile(r"(?<![\w+])\+\d{1,3}[ -]?(?:\(0\)[ -]?)?\d[\d /-]{5,14}\d\b"), 0, None,
     lambda v: f"{v[:3]}…{v[-2:]}"),
    ("personal", "phone number", re.compile(r"(?i)\b(?:phone|tel|mobile|mobil|fax)\.?:?\s*(\(?0\d[\d ()/-]{6,16}\d)"), 1, None,
     lambda v: f"…{v[-2:]}"),
    ("personal", "IP address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 0, _ip_personal, lambda v: f"{v.split('.')[0]}.x.x.x"),
]

KEY_VALUE = re.compile(r"^([ \t]*-?[ \t]*[\"']?([\w.-]+)[\"']?[ \t]*[:=][ \t]*)(\S.*?)[ \t]*$", re.M)

INSTRUCTION = re.compile(
    r"(?i)\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+)*(?:previous|prior|above|earlier|preceding|system)?\s*"
    r"(?:instructions?|rules?|prompts?|guidelines?)"
    r"|\b(?:you are now|from now on you|act as (?:an?|the) (?:ai|assistant|reviewer))"
    r"|\b(?:system prompt|developer message)\b"
    r"|\b(?:mark|report|classify|treat|consider)\s+(?:this|these|all|every|the)\s+(?:\w+\s+){0,4}(?:as\s+)?(?:compliant|approved|passed|covered)\b"
    r"|\bdo not (?:report|flag|mention)\s+(?:any\s+)?(?:gaps?|findings?|issues?|problems?)"
    r"|\b(?:answer|respond|reply|say|state|output)\s+(?:that|with)\b[^.\n]{0,80}?\b(?:satisfied|compliant|approved|passe[sd]|no gaps?)"
    r"|\b(?:every|all|each)\s+rules?\s+(?:is|are)\s+(?:satisfied|met|passed)"
)


def _replace_span(text: str, start: int, end: int, marker: str) -> str:
    """Replace text[start:end] by the marker but keep its newlines, so line numbers stay the same."""
    return text[:start] + marker + "\n" * text[start:end].count("\n") + text[end:]


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


BOUNDARY_BEFORE = re.compile(r"[.!?][\"')]?\s+|\n\s*\n|\n(?=\s*(?:#|[-*]\s|\d+\.\s))")


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow a match to its whole sentence, never crossing a blank line, heading or list item."""
    s = 0
    for b in BOUNDARY_BEFORE.finditer(text, 0, start):
        s = b.end()
    nxt = re.compile(r"[.!?]|\n\s*\n").search(text, end)
    e = len(text) if nxt is None else (nxt.end() if text[nxt.start()] in ".!?" else nxt.start())
    return s, e


def clean(text: str, kind: str = "adr") -> tuple[str, list[Removal]]:
    """Return the cleaned text and what was removed (pattern-based part: secrets, personal data,
    instructions aimed at the AI). Idempotent: markers are never matched again."""
    removals: list[Removal] = []

    def apply(type_: str, label: str, pattern: re.Pattern[str], group: int,
              valid: Callable[[str], bool] | None, preview: Callable[[str], str]) -> None:
        nonlocal text
        for m in reversed(list(pattern.finditer(text))):
            value = m.group(group)
            if not value or "REMOVED_" in value or (valid and not valid(value)):
                continue
            start, end = m.span(group)
            removals.append(Removal(type_, label, _line(text, start), preview(value)))
            text = _replace_span(text, start, end, MARK[type_])

    for rule in RULES[:2]:  # whole blocks and URL credentials before line-level key/value pairs
        apply(*rule)

    # key: value / key=value with a secret-looking key and a literal value (configs, code blocks, prose tables)
    for m in reversed(list(KEY_VALUE.finditer(text))):
        key, value = m.group(2), m.group(3).strip().strip("\"'")
        leaf = key.split(".")[-1]
        if SECRET_KEY.search(leaf) and not PLACEHOLDER.match(value) and "REMOVED_" not in value \
                and not value.startswith(("{", "[")) and value.lower() not in ("true", "false", "null", "none"):
            removals.append(Removal("secret", f"value of {key}", _line(text, m.start(3)), _mask(value, 1)))
            text = _replace_span(text, m.start(3), m.end(3), MARK["secret"])

    for rule in RULES[2:]:
        apply(*rule)

    if kind == "adr":  # instructions aimed at the AI: remove the whole sentence
        spans: list[tuple[int, int]] = []
        for m in INSTRUCTION.finditer(text):  # several triggers can sit in one sentence: merge first
            if "REMOVED_" in m.group(0):
                continue
            start, end = _sentence_span(text, m.start(), m.end())
            if spans and start <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
            else:
                spans.append((start, end))
        for start, end in reversed(spans):
            sentence = " ".join(text[start:end].split())
            removals.append(Removal("instruction", "instruction aimed at the AI", _line(text, start),
                                    " ".join(sentence.split()[:7]) + ("…" if len(sentence.split()) > 7 else "")))
            text = _replace_span(text, start, end, MARK["instruction"])

    removals.sort(key=lambda r: (r.line, r.type))
    return text, removals


# ---- unsafe language: needs a model, so Decider (local) decides ---------------------------------
UNSAFE_TOPIC = ("abusive, hateful, harassing, sexual, violent or self-harm language, or instructions "
                "for causing harm")


def unsafe_question() -> dict:
    from shodhaka import decider as d
    return d.noul(f"Does this section contain {UNSAFE_TOPIC}?",
                  true=f"the section contains {UNSAFE_TOPIC}",
                  false="the section is ordinary business or technical writing")


def remove_unsafe(doc, decider, threshold: float = 0.5, max_per_section: int = 3) -> tuple[str, list[Removal]]:
    """Ask Decider per section; in a flagged section ask which sentence is unsafe and remove it,
    up to `max_per_section` times. Returns the new full text and the removals."""
    from shodhaka import decider as d
    from shodhaka.documents.model import sentences
    from shodhaka.rules.compiler import section_state

    text, removals = doc.text, []
    for section in doc.sections:
        current = section
        for _ in range(max_per_section):
            answer = decider.ask(section_state(doc, current), {"unsafe": unsafe_question()})["unsafe"]
            if answer.p_true < threshold:
                break
            candidates = [s for s in sentences(current.text) if "REMOVED_" not in s][:40]
            if not candidates:
                break
            if len(candidates) == 1:
                worst, conf = candidates[0], answer.p_true
            else:
                keyed = {f"sentence-{i + 1}": s for i, s in enumerate(candidates)}
                pick = decider.ask(section_state(doc, current), {"which": d.choice(
                    f"Which sentence contains {UNSAFE_TOPIC}?", keyed)})["which"]
                worst, conf = keyed[pick.option], pick.confidence
            located = _find_flat(text, worst)
            if located is None:
                break
            start, end = located
            removals.append(Removal("unsafe", "unsafe language", _line(text, start), f"{worst.split()[0]} …",
                                    by="Decider", confidence=round(min(conf, answer.p_true), 3)))
            text = _replace_span(text, start, end, MARK["unsafe"])
            current = type(current)(current.id, current.heading,
                                    current.text.replace(worst, MARK["unsafe"]) if worst in current.text
                                    else _flat_replace(current.text, worst), current.start_line)
    return text, removals


def _find_flat(text: str, sentence: str) -> tuple[int, int] | None:
    """Find a sentence (whitespace-normalised by the splitter) in the original text."""
    pattern = r"\s+".join(re.escape(w) for w in sentence.split())
    m = re.search(pattern, text)
    return m.span() if m else None


def _flat_replace(text: str, sentence: str) -> str:
    span = _find_flat(text, sentence)
    return text if span is None else _replace_span(text, span[0], span[1], MARK["unsafe"])
