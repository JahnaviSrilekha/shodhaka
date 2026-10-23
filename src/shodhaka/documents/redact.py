"""Redact identifying details before any text leaves the machine.

Placeholders are stable within a run ([HOST_1] is always the same host), and the mapping
never leaves the process, so suggestions coming back from Bedrock can be restored locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("URL", re.compile(r"\bhttps?://[^\s)\"'`]+")),
    ("JDBC", re.compile(r"\bjdbc:[a-z0-9]+://[^\s\"'`]+", re.I)),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("HOST", re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|local|corp|lan|intra)\b", re.I)),
    ("KEY", re.compile(r"\b(?:sk|pk|tk|rk|ghp|xox[abp])_[A-Za-z0-9_]{8,}\b")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


@dataclass
class Redactor:
    """Redact text; extra literal terms (vendor or person names) can be added per run."""

    extra_terms: dict[str, str] = field(default_factory=dict)  # term -> label, e.g. {"Stripe": "VENDOR"}
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original
    _reverse: dict[str, str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def _placeholder(self, label: str, original: str) -> str:
        if original in self._reverse:
            return self._reverse[original]
        self._counts[label] = self._counts.get(label, 0) + 1
        token = f"[{label}_{self._counts[label]}]"
        self.mapping[token] = original
        self._reverse[original] = token
        return token

    def redact(self, text: str) -> str:
        for label, pattern in PATTERNS:
            text = pattern.sub(lambda m, label=label: self._placeholder(label, m.group(0)), text)
        for term, label in self.extra_terms.items():
            text = re.sub(re.escape(term), lambda m, label=label: self._placeholder(label, m.group(0)), text)
        return text

    def restore(self, text: str) -> str:
        for token, original in self.mapping.items():
            text = text.replace(token, original)
        return text

    def leaks(self, text: str) -> list[str]:
        """Originals (or still-matching patterns) present in `text`. Empty means safe to send."""
        found = [original for original in self.mapping.values() if original in text]
        for label, pattern in PATTERNS:
            found += [f"{label}:{m.group(0)}" for m in pattern.finditer(text)]
        return found
