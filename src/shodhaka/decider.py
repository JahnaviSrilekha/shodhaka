"""Talk to a locally served Strands Decider 2B.

Start the server on your machine (Apple silicon shown):

    pip install "strands-decider[mlx]"
    strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device mlx --port 8099

The wire format is the server's /v1/systemone endpoint: one `state`, many typed questions,
answers back under the same keys. Everything stays on localhost.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_URL = os.environ.get("STRANDS_DECIDER_URL", "http://127.0.0.1:8099")


class DeciderUnavailable(RuntimeError):
    pass


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict[str, Any]:
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    criteria = {k: v for k, v in (("true", true), ("false", false)) if v}
    if criteria:
        question["criteria"] = criteria
    return question


def choice(instructions: str, criteria: Mapping[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


@dataclass(frozen=True)
class Answer:
    """One answer, normalised. For a yes/no question `option` is "true" or "false"."""

    option: str
    confidence: float
    probabilities: dict[str, float]

    @classmethod
    def from_wire(cls, raw: Mapping[str, Any]) -> "Answer":
        if raw["type"] == "noul":
            p = float(raw["noul"])
            return cls("true" if p >= 0.5 else "false", max(p, 1 - p), {"true": p, "false": 1 - p})
        if raw["type"] == "choice":
            return cls(raw["choice"], float(raw["confidence"]), dict(raw["probabilities"]))
        raise ValueError(f"unsupported answer type {raw['type']!r}")

    @property
    def p_true(self) -> float:
        return self.probabilities.get("true", 0.0)


class Decider(Protocol):
    def ask(self, state: str, questions: Mapping[str, dict[str, Any]]) -> dict[str, Answer]: ...


@dataclass
class Stats:
    calls: int = 0
    questions: int = 0
    input_tokens: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        lat = sorted(self.latencies_ms)

        def pct(q: float) -> float | None:
            if not lat:
                return None
            return round(lat[min(len(lat) - 1, int(round(q * (len(lat) - 1))))], 1)

        return {
            "calls": self.calls,
            "questions": self.questions,
            "input_tokens": self.input_tokens,
            "latency_ms_p50": pct(0.5),
            "latency_ms_p95": pct(0.95),
        }


class HttpDecider:
    """Synchronous client: requests go one at a time, which is how the server is best driven."""

    def __init__(self, url: str = DEFAULT_URL, timeout: float = 120.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.stats = Stats()

    def health(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.url}/health", timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, OSError) as exc:
            raise DeciderUnavailable(
                f"no Strands Decider at {self.url} ({exc}). Start one with:\n"
                "    strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099"
            ) from exc

    def ask(self, state: str, questions: Mapping[str, dict[str, Any]]) -> dict[str, Answer]:
        body = json.dumps({"state": state, "questions": dict(questions)}).encode()
        request = urllib.request.Request(
            f"{self.url}/v1/systemone", data=body, headers={"content-type": "application/json"}
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, OSError) as exc:
            raise DeciderUnavailable(f"Decider request failed: {exc}") from exc
        self.stats.calls += 1
        self.stats.questions += len(questions)
        self.stats.input_tokens += payload.get("usage", {}).get("input_tokens", 0)
        self.stats.latencies_ms.append(payload.get("latency_ms") or (time.perf_counter() - started) * 1000)
        return {key: Answer.from_wire(raw) for key, raw in payload["answers"].items()}


class ScriptedDecider:
    """Test double. `script(state, key, question)` returns (option, confidence)."""

    def __init__(self, script: Callable[[str, str, dict[str, Any]], tuple[str, float]]) -> None:
        self.script = script
        self.stats = Stats()
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def ask(self, state: str, questions: Mapping[str, dict[str, Any]]) -> dict[str, Answer]:
        self.requests.append((state, dict(questions)))
        self.stats.calls += 1
        self.stats.questions += len(questions)
        self.stats.latencies_ms.append(1.0)
        answers = {}
        for key, question in questions.items():
            option, confidence = self.script(state, key, question)
            if question["type"] == "noul":
                p = confidence if option == "true" else 1 - confidence
                answers[key] = Answer(option, confidence, {"true": p, "false": 1 - p})
            else:
                rest = (1 - confidence) / max(1, len(question["criteria"]) - 1)
                probs = {name: (confidence if name == option else rest) for name in question["criteria"]}
                answers[key] = Answer(option, confidence, probs)
        return answers
