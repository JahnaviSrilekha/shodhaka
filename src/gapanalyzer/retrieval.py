"""Optional retrieval: shortlist the sections each rule is checked against.

Without retrieval (the default) every section is checked against every rule, so nothing can be
skipped. That costs sections x rules and stops scaling for long documents or large rule packs.
With retrieval, each rule is checked only against its `top_k` most similar sections; the rest
are recorded as "not checked (retrieval)" — never as compliant.

Methods, all local (nothing leaves the machine):
  * bm25   — keyword ranking, pure Python, no model and no download.
  * minilm — meaning-based ranking with a small embedding model
             (sentence-transformers/all-MiniLM-L6-v2, about 90 MB, downloaded once).
             Needs `pip install -e ".[embed]"` (PyTorch: use Python 3.12).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

from .rulepack import Rule

METHODS = ("none", "bm25", "minilm")
TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was
were will with which who what when where how not no each every only than then there these those
service services""".split())


def rule_query(rule: Rule) -> str:
    """The text a rule is matched with: its topic, requirement and the options' descriptions."""
    parts = [rule.title, rule.requirement]
    if rule.decider:
        parts += [rule.decider.topic] + [o.description for o in rule.decider.options if o.verdict != "not_applicable"]
    return " ".join(p for p in parts if p)


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


class Ranker(Protocol):
    name: str

    def scores(self, query: str, docs: list[str]) -> list[float]: ...


class BM25:
    """Okapi BM25 over one document's sections (k1=1.5, b=0.75)."""

    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b

    def scores(self, query: str, docs: list[str]) -> list[float]:
        tokenised = [tokens(d) for d in docs]
        n = len(tokenised)
        avg = sum(len(t) for t in tokenised) / n if n else 0.0
        df = Counter(term for t in tokenised for term in set(t))
        q = set(tokens(query))
        out = []
        for t in tokenised:
            tf = Counter(t)
            score = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * tf[term] * (self.k1 + 1) / (tf[term] + self.k1 * (1 - self.b + self.b * len(t) / (avg or 1)))
            out.append(score)
        return out


class MiniLM:
    """Cosine similarity with a small local sentence-embedding model."""

    name = "minilm"
    MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model: str = MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                'MiniLM retrieval needs sentence-transformers: pip install -e ".[embed]" (Python 3.12, PyTorch)') from exc
        self._model = SentenceTransformer(model)
        self._cache: dict[str, list[float]] = {}

    def _embed(self, texts: list[str]):
        missing = [t for t in texts if t not in self._cache]
        if missing:
            for text, vector in zip(missing, self._model.encode(missing, normalize_embeddings=True)):
                self._cache[text] = vector
        return [self._cache[t] for t in texts]

    def scores(self, query: str, docs: list[str]) -> list[float]:
        q = self._embed([query])[0]
        return [float((q * d).sum()) for d in self._embed(docs)]


def make_ranker(method: str) -> Ranker | None:
    if method == "none":
        return None
    if method == "bm25":
        return BM25()
    if method == "minilm":
        return MiniLM()
    raise ValueError(f"retrieval must be one of {METHODS}")


def shortlist(ranker: Ranker, rules: list[Rule], section_texts: list[str], top_k: int) -> dict[str, set[int]]:
    """rule id -> indexes of the sections that rule will be checked against."""
    if top_k >= len(section_texts):
        return {r.id: set(range(len(section_texts))) for r in rules}
    picked = {}
    for rule in rules:
        s = ranker.scores(rule_query(rule), section_texts)
        picked[rule.id] = set(sorted(range(len(s)), key=lambda i: -s[i])[:top_k])
    return picked
