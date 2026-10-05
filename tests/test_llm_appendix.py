"""The technical appendix (scripts/llm_appendix): request schema, answer mapping, the chat adapter against a
mock server, the test conditions, the scoring helpers, and that it stays apart from the main deliverables.

Offline: no API calls.
"""
from __future__ import annotations

import json
import re
import sys

import httpx
import pytest

from zeroops import paths
from zeroops import llm_appendix_paths as loc
from zeroops.corpus import corpus_fingerprint, generate_corpus
from zeroops.schema import incident_questions, parse_answers

sys.path.insert(0, str(loc.CODE))
import analyze  # noqa: E402
import chat  # noqa: E402
import conditions  # noqa: E402
import run  # noqa: E402

QS = incident_questions()


def full_reply(action="rollback", p=0.9) -> dict:
    out = {}
    for qid, q in QS.items():
        if q["type"] == "noul":
            out[qid] = {"probability": 0.2}
        elif q["type"] == "choice":
            out[qid] = {"answer": action if qid == "proposed_action" else next(iter(q["criteria"])), "probability": p}
        else:
            out[qid] = {"answer": q["criteria"][1], "probability": p}
    return out


# ---------------------------------------------------------------- schema and mapping

def test_schema_requires_every_question_and_pins_the_options():
    s = chat.answer_schema(QS)
    assert s["required"] == list(QS) and s["additionalProperties"] is False
    for qid, q in QS.items():
        node = s["properties"][qid]
        assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
        if q["type"] == "choice":
            assert node["properties"]["answer"]["enum"] == list(q["criteria"])
        elif q["type"] == "score":
            assert node["properties"]["answer"]["enum"] == list(q["criteria"])   # labels, not integers
        else:
            assert list(node["properties"]) == ["probability"]
    assert not re.search(r'"(minimum|maximum|multipleOf)"', json.dumps(s))


def test_a_full_reply_parses_with_nothing_missing_and_jev_scaled_confidence():
    answers = chat.to_answers(full_reply(p=0.9), QS)
    p = parse_answers(answers)
    assert p.missing == []
    assert p.proposed_action == "rollback"
    assert p.proposed_action_confidence == pytest.approx((0.9 - 1 / 8) / (1 - 1 / 8))
    assert p.severity == 1.0 and p.severity_confidence == pytest.approx(0.9)
    assert p.needs_page == pytest.approx(0.2)


def test_percentages_are_read_and_bad_answers_count_as_missing():
    reply = full_reply(p=85)
    reply["root_cause"]["answer"] = "gremlins"
    reply["needs_page"]["probability"] = "high"
    answers = chat.to_answers(reply, QS)
    assert answers["proposed_action"]["stated"] == pytest.approx(0.85)
    p = parse_answers(answers)
    assert set(p.missing) == {"root_cause", "needs_page"}


# ---------------------------------------------------------------- the adapter against a mock server

def mock_adapter(handler, **kw) -> chat.ChatAdapter:
    a = chat.ChatAdapter("t", "vendor/model", "k", max_attempts=1, **kw)
    a._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
    return a


def ok_response(content: str, **extra) -> httpx.Response:
    return httpx.Response(200, json={
        "model": "vendor/model", "provider": "P", "id": "gen-1",
        "choices": [{"message": {"content": content}, "finish_reason": "stop", **extra}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.0012,
                  "completion_tokens_details": {"reasoning_tokens": 7}}})


def test_request_and_response_round_trip():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        seen["auth"] = req.headers["Authorization"]
        return ok_response(json.dumps(full_reply()))

    r = mock_adapter(handler).decide("state")
    assert r.ok and r.parsed.missing == [] and r.cost_usd == 0.0012
    assert (r.input_tokens, r.output_tokens) == (1000, 200)
    assert seen["auth"] == "Bearer k" and seen["temperature"] == 0
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["provider"] == {"require_parameters": True}
    assert seen["reasoning"] == {"effort": "none"}


def test_refused_settings_fall_back_once_and_stick():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "temperature" in body:
            return httpx.Response(404, json={"error": {"message": "No endpoints found that can handle the requested parameters."}})
        if body["reasoning"]["effort"] == "none":
            return httpx.Response(400, json={"error": {"message": "Reasoning is mandatory for this endpoint"}})
        return ok_response(json.dumps(full_reply()))

    a = mock_adapter(handler)
    assert a.decide("s").ok
    assert (a.temperature, a.reasoning) == (None, "minimal")
    assert a.decide("s").ok and len(bodies) == 4          # the second call goes straight through


def test_a_reply_that_is_not_json_is_an_error():
    r = mock_adapter(lambda req: ok_response("I think it is a rollback.")).decide("s")
    assert not r.ok and "not JSON" in r.error


def test_token_probabilities_map_to_options():
    text = '{"proposed_action": {"answer": "rollback", "probability": 0.9}}'
    pieces = ['{"proposed_action": {"answer": "', "roll", 'back", "probability": 0.9}}']
    assert "".join(pieces) == text
    lp = [{"token": pieces[0], "top_logprobs": []},
          {"token": "roll", "top_logprobs": [{"token": "roll", "logprob": -0.1}, {"token": "patch", "logprob": -2.5},
                                             {"token": "re", "logprob": -3.0}]},
          {"token": pieces[2], "top_logprobs": []}]
    probs = chat.first_token_probs(lp, QS)["proposed_action"]
    assert max(probs, key=probs.get) == "rollback" and sum(probs.values()) == pytest.approx(1, abs=1e-5)
    assert set(probs) <= set(QS["proposed_action"]["criteria"])


# ---------------------------------------------------------------- conditions

def test_base_corpus_is_untouched():
    assert corpus_fingerprint(conditions.incidents("base")) == "0b4839761e06"


@pytest.mark.parametrize("name", ["injected", "harder"])
def test_stress_sets_keep_labels_and_change_only_the_text(name):
    base, altered = conditions.incidents("base"), conditions.incidents(name)
    assert [(i.id, i.ground_truth) for i in base] == [(i.id, i.ground_truth) for i in altered]
    assert all(a.state != b.state for a, b in zip(base, altered))


def test_injection_adds_one_log_line():
    for b, i in zip(conditions.incidents("base"), conditions.incidents("injected")):
        assert i.state.count(conditions.INJECTION) == 1
        logs = i.state.split("LOGS:\n")[1].split("\n\n")[0]
        assert conditions.INJECTION in logs and b.state.split("LOGS:\n")[1].split("\n\n")[0] in logs


def test_harder_covers_every_scenario_type():
    assert set(conditions.HARDER) == {i.archetype for i in generate_corpus(4)}


def test_shuffled_questions_are_reproducible_and_keep_the_options():
    state = generate_corpus(4)[0].state
    a, b = conditions.shuffled_questions(state), conditions.shuffled_questions(state)
    assert a == b
    for qid, q in QS.items():
        assert set(a[qid].get("criteria") or []) == set(q.get("criteria") or [])
        if q["type"] == "score":
            assert a[qid]["criteria"] == q["criteria"]
    orders = {tuple(conditions.shuffled_questions(i.state)["proposed_action"]["criteria"]) for i in generate_corpus(4)}
    assert len(orders) > 10


def test_the_shuffle_wrapper_sends_the_shuffled_questions():
    sent = []

    class Fake:
        name = "fake"

        def decide(self, state, questions=None):
            sent.append(questions)

    conditions.Shuffled(Fake()).decide("some state")
    assert sent[0] == conditions.shuffled_questions("some state")


# ---------------------------------------------------------------- scoring

def test_confidence_quality_on_known_inputs():
    perfect = analyze.confidence_quality([(0.9, True), (0.8, True), (0.2, False), (0.1, False)])
    assert perfect["auroc"] == 1.0 and perfect["selective_accuracy_pct"]["50"] == 100.0
    ties = analyze.confidence_quality([(0.9, True), (0.9, False), (0.9, True), (0.9, False)])
    assert ties["auroc"] == 0.5 and ties["selective_accuracy_pct"]["25"] == 50.0
    assert ties["ece"] == pytest.approx(0.4) and ties["brier"] == pytest.approx(0.41)


def test_failed_records_are_retried_on_resume(tmp_path):
    log = tmp_path / "x.jsonl"
    log.write_text(json.dumps({"incident_id": "INC-0001", "error": None}) + "\n"
                   + json.dumps({"incident_id": "INC-0002", "error": "HTTP 503"}) + "\n")
    assert list(run.read_log(log)) == ["INC-0001"]


def test_cost_estimate_is_positive_for_every_backend():
    assert all(run.estimate(b, 10) > 0 for b in run.BACKENDS)


# ---------------------------------------------------------------- kept apart from the main deliverables

def test_appendix_writes_nowhere_the_main_pipeline_reads():
    assert loc.RESULTS.parent == paths.RESULTS                      # a subfolder: report.py globs the top level only
    assert not re.match(r"[0-9]_", loc.OUTPUT.name)                  # unnumbered: the numbered set is fixed
    assert loc.OUTPUT.parent == paths.DELIVERABLES and loc.SCRATCH.parent == paths.SCRATCH
    assert not any(n.startswith("decisions_") for n in (loc.log("x", "base").name, loc.log("x", "harder").name))


def test_appendix_code_follows_the_project_path_rules():
    joined = re.compile(r"\bROOT\s*/\s*[\"']")
    old = "dem" + "o"
    old_path = re.compile(r"(?<!\w)" + old + r"/|[\"']" + old + r"[\"']")
    for f in sorted(loc.CODE.glob("*.py")):
        text = f.read_text()
        assert not joined.search(text), f.name
        assert not old_path.search(text), f.name
