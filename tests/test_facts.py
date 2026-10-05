"""Facts and report generation on oracle records (no network, no models)."""
import importlib.util

from zeroops import paths
from zeroops.corpus import corpus_fingerprint
from zeroops.facts import build_facts, parsed_from_pred
from zeroops.metrics import compute_metrics
from zeroops.orchestrator import run_incident
from zeroops.policy import decide

from test_pipeline import CORPUS, OracleAdapter

VERSION = corpus_fingerprint(CORPUS)
RECS = [run_incident(OracleAdapter(CORPUS), inc, corpus_version=VERSION) for inc in CORPUS]


def _report_module():
    path = paths.SCRIPTS / "report.py"
    spec = importlib.util.spec_from_file_location("report_script", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parsed_from_pred_round_trips_the_decision():
    for r in RECS:
        assert decide(parsed_from_pred(r["pred"]), r["thresholds"]).outcome == r["decision"]["outcome"]


def test_build_facts_shapes():
    per = {"jev_native": RECS}
    facts = build_facts(per, {"jev_native": compute_metrics(RECS)}, VERSION)
    assert facts["n"] == 56 and facts["n_templates"] == 14 and facts["n_unsafe"] == 20
    b = facts["backends"]["jev_native"]
    assert b["unsafe_auto"] == 0 and b["missed_incidents"] == 0
    j = facts["jev"]
    assert j["first_listed_action"] == "rollback"
    assert j["examples"]["stopped"]["archetype"] == "data_corruption"
    assert all("margin" in c for c in j["examples"]["stopped"]["checks"])


def test_report_handles_a_backend_that_never_acts():
    # every answer says "escalate": no AUTO, so several rates are undefined
    never = []
    for r in RECS:
        r2 = {**r, "pred": {**r["pred"], "proposed_action": "escalate"},
              "decision": {**r["decision"], "outcome": "ESCALATE", "rationale": "model proposes escalate"}}
        never.append(r2)
    per = {"jev_native": RECS, "laya_local": never}
    metrics = {k: compute_metrics(v) for k, v in per.items()}
    for m in metrics.values():
        m["cost"]["basis"] = "test"
    facts = build_facts(per, metrics, VERSION)
    md = _report_module().build_report_md(per, metrics, facts)
    assert "never acted" in md and "Laya" in md
