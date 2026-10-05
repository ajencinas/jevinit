"""A general LLM behind the same interface as Jev: one OpenRouter chat call answers the 12 questions.

The model gets the same incident state and the same questions (instructions and option descriptions)
that Jev gets, plus a strict JSON schema that pins every choice to its options. Its reply is turned into
System One shaped answers, so `parse_answers`, the gate and the metrics apply unchanged.

Confidence: a chat model returns no probabilities, so the schema asks for one per answer (the
probability that the answer is correct), as Now Assist's assignment prediction does with its
"Confidence Score". Jev's choice confidence is not p_max but (p_max - 1/n) / (1 - 1/n) (TypeSafe docs,
confidence.md); the stated probability of a choice is put on the same scale before it reaches the gate. Where the
endpoint returns token log probabilities, the first token of the action and category answers gives
a second, measured distribution (`logprob_probs`).
"""
from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx

from zeroops.adapters import DecisionResult, SystemOneAdapter
from zeroops.schema import Parsed, incident_questions, parse_answers

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = (
    "You are the decision step in an automated IT incident workflow. Read the incident state and answer "
    "every question in the JSON you are given, using only the incident state.\n"
    "- choice questions: answer with exactly one option key from the question's criteria.\n"
    "- score questions: answer with one level, copied exactly from the question's criteria.\n"
    "- noul questions: give the probability (0 to 1) that the statement in the instructions is true.\n"
    "For every choice and score answer, also give the probability (0 to 1) that your answer is correct.\n"
    "Return only the JSON object."
)
LOGPROB_QUESTIONS = ("proposed_action", "failure_category")


def answer_schema(questions: dict[str, dict]) -> dict:
    """Strict JSON schema: every question required, choices limited to their options (in the order given)."""
    props = {}
    for qid, q in questions.items():
        if q["type"] == "choice":
            answer = {"type": "string", "enum": list(q["criteria"])}
        elif q["type"] == "score":
            answer = {"type": "string", "enum": list(q["criteria"])}  # the level's label; integer enums fail on Gemini
        if q["type"] == "noul":
            fields = {"probability": {"type": "number", "description": "probability the statement is true, 0 to 1"}}
        else:
            fields = {"answer": answer,
                      "probability": {"type": "number", "description": "probability the answer is correct, 0 to 1"}}
        props[qid] = {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def request_body(model: str, state: str, questions: dict[str, dict], reasoning: str | None,
                 logprobs: bool = False, temperature: float | None = 0) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": json.dumps({"incident": state, "questions": questions}, indent=1)}],
        "stream": False,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "incident_decision", "strict": True,
                                            "schema": answer_schema(questions)}},
        "provider": {"require_parameters": True},
    }
    if temperature is not None:
        body["temperature"] = temperature
    if reasoning:
        body["reasoning"] = {"effort": reasoning}
    if logprobs:
        body["logprobs"], body["top_logprobs"] = True, 5
    return body


def unit(x: Any) -> float | None:
    """A probability as a float in [0, 1], accepting 0-100 percentages; None if unusable."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    if 1 < v <= 100:
        v /= 100
    return min(max(v, 0.0), 1.0)


def jev_scale(p: float, n: int) -> float:
    """Jev's choice/score confidence for a top probability p over n options."""
    return max(0.0, (p - 1 / n) / (1 - 1 / n)) if n > 1 else p


def to_answers(reply: dict, questions: dict[str, dict], logprob_probs: dict[str, dict] | None = None) -> dict:
    """The model's JSON reply as System One answers. Unusable fields are left out, so they count as missing."""
    out = {}
    for qid, q in questions.items():
        a = reply.get(qid)
        if not isinstance(a, dict):
            continue
        p = unit(a.get("probability"))
        if q["type"] == "noul":
            if p is not None:
                out[qid] = {"type": "noul", "noul": p}
            continue
        value, n = a.get("answer"), len(q["criteria"])
        if p is None or value is None:
            continue
        if q["type"] == "choice":
            probs = (logprob_probs or {}).get(qid) or {value: p}
            out[qid] = {"type": "choice", "choice": value, "confidence": jev_scale(p, n), "probabilities": probs,
                        "stated": p}
        elif value in q["criteria"]:
            level = q["criteria"].index(value)
            # Jev's score confidence is the probability of the nearest level, not rescaled like a choice
            out[qid] = {"type": "score", "score": level, "confidence": p, "probabilities": {str(level): p},
                        "stated": p}
    return out


def first_token_probs(content_logprobs: list[dict], questions: dict[str, dict]) -> dict[str, dict]:
    """Per-option probabilities for a few choice questions, read from the top log probabilities of the
    first token of each answer value. A token counts for an option when the option starts with it and
    no other option does; the mass found is renormalised. Questions that cannot be mapped are left out."""
    tokens = [t.get("token", "") for t in content_logprobs]
    text, starts = "", []
    for tok in tokens:
        starts.append(len(text))
        text += tok
    out = {}
    for qid in LOGPROB_QUESTIONS:
        key = f'"{qid}"'
        at = text.find(key)
        if at < 0:
            continue
        ans = text.find('"answer"', at)
        colon = text.find(":", ans)
        quote = text.find('"', colon + 1)
        if min(ans, colon, quote) < 0:
            continue
        # the token that carries the first character of the answer value
        i = max(j for j, s in enumerate(starts) if s <= quote + 1)
        options = list(questions[qid]["criteria"])
        mass: dict[str, float] = {}
        for alt in content_logprobs[i].get("top_logprobs") or []:
            stem = alt.get("token", "").replace('"', "").strip()
            hits = [o for o in options if stem and o.startswith(stem)]
            if len(hits) == 1:
                mass[hits[0]] = mass.get(hits[0], 0.0) + math.exp(alt.get("logprob", -99))
        total = sum(mass.values())
        if total > 0:
            out[qid] = {o: round(v / total, 6) for o, v in sorted(mass.items(), key=lambda kv: -kv[1])}
    return out


class ChatAdapter(SystemOneAdapter):
    """OpenRouter chat completions with strict structured output; keeps one keep-alive connection, as the
    Jev adapter does, so latency compares like with like. `last` holds the latest raw exchange."""

    RETRYABLE = (408, 429, 500, 502, 503, 504, 524, 529)

    def __init__(self, name: str, model: str, api_key: str, reasoning: str | None = "none",
                 logprobs: bool = False, timeout: float = 120.0, max_attempts: int = 3, endpoint: str = CHAT_URL):
        self.name, self.model, self.api_key = name, model, api_key
        self.reasoning, self.logprobs, self.temperature = reasoning, logprobs, 0
        self.endpoint, self.max_attempts = endpoint, max(1, max_attempts)
        self._client = httpx.Client(timeout=timeout)
        self.last: dict[str, Any] = {}

    def _post(self, body: dict) -> tuple[httpx.Response | None, float, str | None, int]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        err = None
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                time.sleep(2.0 * (attempt - 1))
            t0 = time.perf_counter()
            try:
                r = self._client.post(self.endpoint, headers=headers, json=body)
            except httpx.HTTPError as e:
                err = repr(e)
                continue
            dt = (time.perf_counter() - t0) * 1000
            if r.status_code == 200:
                return r, dt, None, attempt
            err = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code not in self.RETRYABLE:
                return None, dt, err, attempt
        return None, 0.0, err, self.max_attempts

    def decide(self, state: str, questions: dict[str, Any] | None = None) -> DecisionResult:
        questions = questions or incident_questions()

        def call():
            return self._post(request_body(self.model, state, questions, self.reasoning, self.logprobs,
                                           self.temperature))
        r, dt, err, attempts = call()
        # Settings some endpoints refuse; each fallback sticks for later calls and is recorded.
        if err and self.temperature is not None and err.startswith("HTTP 404") and "No endpoints" in err:
            self.temperature = None           # reasoning models (GPT-6 family) take no temperature
            r, dt, err, attempts = call()
        if err and self.reasoning == "none" and "reasoning" in err.lower():
            self.reasoning = "minimal"        # reasoning cannot be switched off; use the lowest setting
            r, dt, err, attempts = call()
        self.last = {"reasoning": self.reasoning, "temperature": self.temperature, "schema_ok": False}
        if err:
            return DecisionResult(self.name, Parsed(), latency_ms=dt, attempts=attempts, error=err)
        try:
            data = r.json()
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            return DecisionResult(self.name, Parsed(), latency_ms=dt, attempts=attempts,
                                  error=f"unexpected response: {r.text[:200]}")
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        self.last.update(content=content, provider=data.get("provider", ""), generation_id=data.get("id", ""),
                         reasoning_tokens=int(details.get("reasoning_tokens") or 0),
                         finish_reason=choice.get("finish_reason"))
        common = dict(latency_ms=dt, cost_usd=usage.get("cost"), model=data.get("model", self.model),
                      provider=data.get("provider", ""), input_tokens=int(usage.get("prompt_tokens") or 0),
                      output_tokens=int(usage.get("completion_tokens") or 0), attempts=attempts)
        try:
            reply = json.loads(content.strip().removeprefix("```json").removesuffix("```"))
        except ValueError:
            return DecisionResult(self.name, Parsed(), raw=data, error=f"reply is not JSON: {content[:200]}",
                                  **common)
        if not isinstance(reply, dict):
            return DecisionResult(self.name, Parsed(), raw=data, error="reply is not a JSON object", **common)
        lp = (choice.get("logprobs") or {}).get("content")
        logprob_probs = first_token_probs(lp, questions) if lp else {}
        answers = to_answers(reply, questions, logprob_probs)
        parsed = parse_answers(answers)
        self.last.update(answers=answers, logprob_probs=logprob_probs, schema_ok=not parsed.missing)
        return DecisionResult(self.name, parsed, raw={"answers": answers}, **common)
