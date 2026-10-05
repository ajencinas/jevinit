"""Backends, all behind one interface.

TypeSafe native, Jev-on-OpenRouter, Kev and Laya all speak the same System One
wire protocol (POST {endpoint} with {model, state, questions} -> {answers, usage}),
so a single HTTP adapter covers every backend; only the URL/key/model differ.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from .schema import Parsed, parse_answers, incident_questions


@dataclass
class DecisionResult:
    backend: str
    parsed: Parsed
    raw: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float | None = None
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class SystemOneAdapter(ABC):
    name: str

    @abstractmethod
    def decide(self, state: str, questions: dict[str, Any] | None = None) -> DecisionResult: ...


class HttpSystemOneAdapter(SystemOneAdapter):
    """POST {endpoint} with the System One schema. Works for every backend.

    `max_attempts` is the total number of tries (not retries). Transient failures (network
    errors, 429/5xx) are retried with a short backoff; client errors, non-JSON bodies and
    responses without answers are returned as errors immediately.
    """

    RETRYABLE = (429, 500, 502, 503, 524, 529)

    def __init__(self, name: str, endpoint: str, api_key: str = "",
                 model: str = "jev-latest", timeout: float = 120.0, max_attempts: int = 2):
        self.name = name
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self._client = httpx.Client(timeout=timeout)

    def decide(self, state: str, questions: dict[str, Any] | None = None) -> DecisionResult:
        questions = questions or incident_questions()
        body = {"model": self.model, "state": state, "questions": questions}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_err = None
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                time.sleep(1.5 * (attempt - 1))
            t0 = time.perf_counter()
            try:
                r = self._client.post(self.endpoint, headers=headers, json=body)
            except httpx.HTTPError as e:
                last_err = repr(e)
                continue
            dt = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code in self.RETRYABLE:
                    continue
                return DecisionResult(self.name, Parsed(), latency_ms=dt,
                                      attempts=attempt, error=last_err)
            try:
                data = r.json()
            except ValueError:
                return DecisionResult(self.name, Parsed(), latency_ms=dt, attempts=attempt,
                                      error=f"non-JSON 200 response: {r.text[:200]}")
            answers = data.get("answers") if isinstance(data, dict) else None
            if not answers:
                return DecisionResult(self.name, Parsed(), raw=data if isinstance(data, dict) else {},
                                      latency_ms=dt, attempts=attempt,
                                      error="200 response without answers")
            usage = data.get("usage") or {}
            return DecisionResult(
                backend=self.name,
                parsed=parse_answers(answers),
                raw=data,
                latency_ms=dt,
                cost_usd=usage.get("cost"),
                model=data.get("model", self.model),
                provider=data.get("provider", ""),
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                attempts=attempt,
            )
        return DecisionResult(self.name, Parsed(), error=last_err, attempts=self.max_attempts)


def _key(*names: str) -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return ""


# Pinned model versions. `jev-latest` moves with each release and can shift every number
# under you, so evaluations name the version explicitly (override via .env).
JEV_NATIVE_MODEL = "jev-1.13.0"
JEV_OPENROUTER_MODEL = "typesafe/jev-1.13-20260917"


def native_adapter() -> HttpSystemOneAdapter:
    return HttpSystemOneAdapter(
        "jev_native",
        os.getenv("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone"),
        _key("TYPESAFE_API", "TYPESAFE_API_KEY"),
        model=os.getenv("TYPESAFE_MODEL", JEV_NATIVE_MODEL),
    )


def openrouter_adapter() -> HttpSystemOneAdapter:
    return HttpSystemOneAdapter(
        "jev_openrouter",
        "https://openrouter.ai/api/v1/systemone",
        _key("OPENROUTER_API", "OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_JEV_MODEL", JEV_OPENROUTER_MODEL),
    )


def _kev_port() -> int:
    return int(os.getenv("KEV_PORT", "8009"))


def kev_adapter(port: int | None = None) -> HttpSystemOneAdapter:
    port = port or _kev_port()
    return HttpSystemOneAdapter(
        "kev", f"http://127.0.0.1:{port}/v1/systemone",
        _key("KEV_API_KEY"), model="kev-latest", timeout=300.0,
    )


def laya_adapter(port: int = 8010) -> HttpSystemOneAdapter:
    return HttpSystemOneAdapter(
        "laya", f"http://127.0.0.1:{port}/v1/systemone",
        _key("LAYA_API_KEY"), model="english", timeout=300.0,
    )


def api_adapters() -> list[SystemOneAdapter]:
    """The two proprietary paths, in the order we test them."""
    out: list[SystemOneAdapter] = []
    if _key("TYPESAFE_API", "TYPESAFE_API_KEY"):
        out.append(native_adapter())
    if _key("OPENROUTER_API", "OPENROUTER_API_KEY"):
        out.append(openrouter_adapter())
    return out


class LayaLocalAdapter(SystemOneAdapter):
    """In-process Laya Router (no server). Laya speaks the same typed question dict."""

    name = "laya_local"

    def __init__(self, default_model: str | None = None, predict_model: str | None = None,
                 device: str | None = None):
        self._router = None
        self._default_model = default_model
        self._predict_model = predict_model
        self._device = device

    def _get_router(self):
        if self._router is None:
            from laya import Router  # imported lazily; heavy
            kw: dict[str, Any] = {}
            if self._default_model:
                kw["default"] = self._default_model
            if self._device:
                kw["device"] = self._device
            self._router = Router(**kw)
        return self._router

    def decide(self, state: str, questions: dict[str, Any] | None = None) -> DecisionResult:
        questions = questions or incident_questions()
        t0 = time.perf_counter()
        try:
            kw = {"model": self._predict_model} if self._predict_model else {}
            res = self._get_router().predict(state, questions, **kw)
        except Exception as e:  # noqa: BLE001
            return DecisionResult(self.name, Parsed(), error=repr(e))
        dt = (time.perf_counter() - t0) * 1000
        answers = res.get("answers") or {}
        if not answers:
            return DecisionResult(self.name, Parsed(), raw=res, latency_ms=dt,
                                  error="Laya returned no answers")
        # Normalise Laya's confidence to "probability of the chosen answer" so the
        # policy thresholds are comparable with Jev (Laya's `confidence` is 1-entropy).
        for a in answers.values():
            if a.get("type") in ("choice", "score") and "answer_confidence" in a:
                a["confidence"] = a["answer_confidence"]
        usage = res.get("usage") or {}
        routing = res.get("routing") or {}
        return DecisionResult(
            backend=self.name,
            parsed=parse_answers(answers),
            raw=res,
            latency_ms=dt,
            cost_usd=0.0,
            model=routing.get("model", "laya"),
            provider="laya-local",
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
        )


def kev_available(port: int | None = None) -> bool:
    port = port or _kev_port()
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=2.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def local_adapters(with_kev: bool = True) -> list[SystemOneAdapter]:
    """Local open backends: Laya (in-process) and Kev (HTTP) when its server is up."""
    out: list[SystemOneAdapter] = [
        LayaLocalAdapter(
            default_model=os.getenv("LAYA_ROUTER_DEFAULT"),
            predict_model=os.getenv("LAYA_MODEL"),
            device=os.getenv("LAYA_DEVICE"),
        )
    ]
    if with_kev and kev_available():
        out.append(kev_adapter())
    return out
