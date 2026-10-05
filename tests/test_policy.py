from zeroops.policy import AUTO, ESCALATE, OBSERVE, decide
from zeroops.schema import Parsed


def base(**kw) -> Parsed:
    p = Parsed(
        real_incident=0.95, failure_category="config", failure_category_confidence=0.9,
        suspect_component="checkout-api", root_cause="bad_deploy",
        deploy_correlated=0.9, severity=2.0, severity_confidence=0.8, blast_radius=1.0,
        customer_impact=0.8, safe_to_autorollback=0.9, proposed_action="rollback",
        proposed_action_confidence=0.95, action_risk=0.1, needs_page=0.2,
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def test_safe_rollback_automates():
    assert decide(base()).outcome == AUTO


def test_safe_scale_up_automates():
    assert decide(base(proposed_action="scale_up", root_cause="resource_exhaustion",
                       deploy_correlated=0.1)).outcome == AUTO


def test_not_real_incident_observes():
    assert decide(base(real_incident=0.1)).outcome == OBSERVE


def test_high_page_pct_escalates():
    assert decide(base(needs_page=0.95)).outcome == ESCALATE


def test_escalate_action_escalates():
    assert decide(base(proposed_action="escalate")).outcome == ESCALATE


def test_failover_not_auto_approved_escalates():
    assert decide(base(proposed_action="failover")).outcome == ESCALATE


def test_low_action_confidence_escalates():
    assert decide(base(proposed_action_confidence=0.4)).outcome == ESCALATE


def test_high_risk_escalates():
    assert decide(base(action_risk=2.0)).outcome == ESCALATE


def test_sev1_escalates():
    assert decide(base(severity=3.0)).outcome == ESCALATE


def test_rollback_gate_needs_safety():
    assert decide(base(safe_to_autorollback=0.3)).outcome == ESCALATE
    assert decide(base(deploy_correlated=0.2)).outcome == ESCALATE


def test_threshold_override_changes_decision():
    from zeroops.policy import DEFAULT_THRESHOLDS
    th = {**DEFAULT_THRESHOLDS, "action_conf_min": 0.99}
    assert decide(base(proposed_action_confidence=0.95), th).outcome == ESCALATE


def test_escalate_proposal_beats_low_real_incident():
    # Kev-4B, first run: "escalate" on data corruption was logged as noise
    d = decide(base(real_incident=0.3, proposed_action="escalate"))
    assert d.outcome == ESCALATE


def test_high_page_beats_low_real_incident():
    assert decide(base(real_incident=0.3, needs_page=0.95)).outcome == ESCALATE


def test_missing_gating_answer_escalates():
    assert decide(base(missing=["needs_page"])).outcome == ESCALATE


def test_missing_non_gating_answer_does_not_block():
    assert decide(base(missing=["blast_radius"])).outcome == AUTO


def test_explain_reports_margins_for_every_check():
    from zeroops.policy import explain
    rows = explain(base(needs_page=0.88, safe_to_autorollback=0.73))
    by = {r["check"]: r for r in rows}
    assert by["needs_page"]["passed"] and abs(by["needs_page"]["margin"] - 0.02) < 1e-9
    assert by["safe_to_autorollback"]["passed"] and abs(by["safe_to_autorollback"]["margin"] - 0.03) < 1e-9
    assert "deploy_correlated" in by
    assert "deploy_correlated" not in {r["check"] for r in explain(base(proposed_action="scale_up"))}
