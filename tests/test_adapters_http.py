import json

import httpx

from zeroops.adapters import HttpSystemOneAdapter

ANSWERS = {
    "real_incident": {"type": "noul", "noul": 0.9},
    "failure_category": {"type": "choice", "choice": "config", "confidence": 0.9,
                         "probabilities": {"config": 0.9}},
    "severity": {"type": "score", "score": 2.1, "confidence": 0.7},
    "proposed_action": {"type": "choice", "choice": "rollback", "confidence": 0.95,
                        "probabilities": {"rollback": 0.95}},
}


def _adapter(handler, **kw):
    kw.setdefault("max_attempts", 1)
    a = HttpSystemOneAdapter("test", "http://x/v1/systemone", model="jev-latest", **kw)
    a._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
    return a


def test_success_parses_answers_and_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        payload = json.loads(request.read().decode())
        assert payload["model"] == "jev-latest" and "questions" in payload and "state" in payload
        return httpx.Response(200, json={"model": "jev-1.13.0", "provider": "TypeSafe",
                                         "answers": ANSWERS,
                                         "usage": {"input_tokens": 100, "output_tokens": 50, "cost": 0.001}})

    a = _adapter(handler)
    a.api_key = "secret"
    res = a.decide("ignored")
    assert res.ok
    assert res.parsed.real_incident == 0.9
    assert res.parsed.proposed_action == "rollback"
    assert res.cost_usd == 0.001
    assert res.input_tokens == 100 and res.output_tokens == 50
    assert res.provider == "TypeSafe"
    assert res.latency_ms >= 0


def test_client_error_returns_not_ok():
    a = _adapter(lambda req: httpx.Response(400, json={"error": "bad"}))
    res = a.decide("x")
    assert not res.ok
    assert "400" in res.error


def test_server_error_returns_not_ok():
    a = _adapter(lambda req: httpx.Response(503, text="unavailable"))
    res = a.decide("x")
    assert not res.ok
    assert "503" in res.error


def test_empty_answers_is_an_error():
    a = _adapter(lambda req: httpx.Response(200, json={"answers": {}, "usage": {}}))
    res = a.decide("x")
    assert not res.ok and "without answers" in res.error


def test_non_json_200_is_an_error():
    a = _adapter(lambda req: httpx.Response(200, text="<html>oops</html>"))
    res = a.decide("x")
    assert not res.ok and "non-JSON" in res.error


def test_retries_transient_then_succeeds_without_trailing_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr("zeroops.adapters.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"answers": ANSWERS, "usage": {}})

    res = _adapter(handler, max_attempts=3).decide("x")
    assert res.ok and res.attempts == 2
    assert sleeps == [1.5]  # one backoff between attempts, none after success


def test_exhausted_retries_do_not_sleep_after_last_attempt(monkeypatch):
    sleeps = []
    monkeypatch.setattr("zeroops.adapters.time.sleep", lambda s: sleeps.append(s))
    res = _adapter(lambda req: httpx.Response(503, text="busy"), max_attempts=2).decide("x")
    assert not res.ok and res.attempts == 2
    assert sleeps == [1.5]
