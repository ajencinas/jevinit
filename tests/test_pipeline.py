"""End-to-end pipeline test with an oracle adapter (no network, no models)."""
from zeroops.adapters import DecisionResult, SystemOneAdapter
from zeroops.corpus import generate_corpus
from zeroops.metrics import compute_metrics
from zeroops.orchestrator import run_incident
from zeroops.schema import parse_answers

CORPUS = generate_corpus(n_variants=4)


def _oracle_answers(gt: dict) -> dict:
    real = gt["real_incident"]
    safe = gt["auto_safe"]
    return {
        "real_incident": {"type": "noul", "noul": 0.95 if real else 0.05},
        "failure_category": {"type": "choice", "choice": gt["failure_category"],
                             "confidence": 0.9, "probabilities": {gt["failure_category"]: 0.9}},
        "suspect_component": {"type": "choice", "choice": gt["suspect_component"], "confidence": 0.8},
        "root_cause": {"type": "choice", "choice": gt["root_cause"], "confidence": 0.9},
        "deploy_correlated": {"type": "noul", "noul": 0.9 if gt["root_cause"] == "bad_deploy" else 0.2},
        "severity": {"type": "score", "score": float(gt["severity"]), "confidence": 0.8},
        "blast_radius": {"type": "score", "score": 1.0},
        "customer_impact": {"type": "noul", "noul": 0.9 if real else 0.1},
        "safe_to_autorollback": {"type": "noul", "noul": 0.9 if safe else 0.2},
        "proposed_action": {"type": "choice", "choice": gt["correct_action"],
                            "confidence": 0.95, "probabilities": {gt["correct_action"]: 0.95}},
        "action_risk": {"type": "score", "score": 0.1 if safe else 2.0},
        "needs_page": {"type": "noul", "noul": 0.2 if safe else 0.6},
    }


class OracleAdapter(SystemOneAdapter):
    name = "oracle"

    def __init__(self, corpus):
        self.by_state = {i.state: _oracle_answers(i.ground_truth) for i in corpus}

    def decide(self, state, questions=None):
        raw = self.by_state[state]
        return DecisionResult(self.name, parse_answers(raw), raw={"answers": raw},
                              latency_ms=1.0, cost_usd=0.0, model="oracle", provider="test")


def test_oracle_runs_full_corpus():
    recs = [run_incident(OracleAdapter(CORPUS), inc) for inc in CORPUS]
    assert len(recs) == 56
    assert all(r["error"] is None for r in recs)


def test_oracle_is_safe_and_automates():
    recs = [run_incident(OracleAdapter(CORPUS), inc) for inc in CORPUS]
    m = compute_metrics(recs)
    assert m["n"] == 56
    assert m["errors"] == 0
    # perfect oracle: no unsafe automation, and it does automate some cases
    assert m["autonomy"]["unsafe_auto_rate_pct"] == 0
    assert m["autonomy"]["auto_rate_pct"] > 0
    # every unsafe case must be escalated, not observed/automated
    assert m["autonomy"]["escalation_recall_pct"] == 100
    # quality should be perfect on this oracle
    assert m["decision_quality_pct"]["failure_category"] == 100
    assert m["decision_quality_pct"]["action_acceptable"] == 100
    assert m["decision_quality_pct"]["root_cause"] == 100


def test_observe_on_flukes():
    recs = [run_incident(OracleAdapter(CORPUS), inc) for inc in CORPUS]
    flukes = [r for r in recs if not r["ground_truth"]["real_incident"]]
    assert flukes and all(r["decision"]["outcome"] == "OBSERVE" for r in flukes)


class BrokenAdapter(SystemOneAdapter):
    name = "broken"

    def decide(self, state, questions=None):
        from zeroops.schema import Parsed
        return DecisionResult(self.name, Parsed(), error="HTTP 503")


def test_backend_error_escalates():
    rec = run_incident(BrokenAdapter(), CORPUS[0])
    assert rec["error"] and rec["decision"]["outcome"] == "ESCALATE"


def test_records_carry_corpus_version_and_thresholds():
    rec = run_incident(OracleAdapter(CORPUS), CORPUS[0], corpus_version="abc123")
    assert rec["corpus_version"] == "abc123" and rec["thresholds"]["page_min"] == 0.90
