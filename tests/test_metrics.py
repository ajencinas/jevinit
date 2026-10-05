from zeroops.metrics import compute_metrics


def _rec(arch, pred_action, auto_safe, outcome, action_correct, cat_correct,
         cat_conf=0.9, cost=None, latency=100, status=None):
    return {
        "incident_id": "x", "archetype": arch, "backend": "b", "error": None,
        "latency_ms": latency, "cost_usd": cost, "input_tokens": 10,
        "pred": {"failure_category": "config" if cat_correct else "app",
                 "category_confidence": cat_conf, "proposed_action": pred_action,
                 "severity": 2.0, "severity_confidence": 0.8, "real_incident": 0.9},
        "decision": {"outcome": outcome, "action": pred_action, "rationale": "", "gates": {}},
        "ground_truth": {"failure_category": "config", "root_cause": "bad_deploy",
                         "suspect_component": "x", "severity": 2, "correct_action": pred_action,
                         "auto_safe": auto_safe, "real_incident": True},
        "correct": {"real_incident": True, "failure_category": cat_correct, "root_cause": True,
                    "suspect_component": True, "action": action_correct, "severity_abs_err": 0.0},
    }


def test_unsafe_auto_detected():
    recs = [
        _rec("bad_deploy", "rollback", True, "AUTO", True, True),
        _rec("data_corruption", "rollback", False, "AUTO", True, True),  # unsafe auto!
        _rec("security_incident", "escalate", False, "ESCALATE", True, True),
    ]
    m = compute_metrics(recs)
    assert m["autonomy"]["auto"] == 2
    assert m["autonomy"]["unsafe_auto_rate_pct"] == 50  # 1 of 2 autos unsafe
    assert m["autonomy"]["escalation_recall_pct"] == 50  # 1 of 2 unsafe cases escalated


def test_action_acceptable_uses_alternative_set():
    # config_drift's correct action is patch_config, but rollback is acceptable
    r = _rec("config_drift", "rollback", True, "AUTO", False, True)
    r["ground_truth"]["correct_action"] = "patch_config"
    m = compute_metrics([r])
    assert m["decision_quality_pct"]["action"] == 0
    assert m["decision_quality_pct"]["action_acceptable"] == 100


def test_calibration_and_cost():
    recs = [_rec("bad_deploy", "rollback", True, "AUTO", True, True, cat_conf=0.9, cost=0.00002),
            _rec("bad_deploy", "rollback", True, "AUTO", True, True, cat_conf=0.6, cost=0.00002)]
    m = compute_metrics(recs)
    assert m["cost"]["has_cost"] and m["cost"]["total_usd"] > 0
    assert m["cost"]["per_1k_usd"] == round(0.00002 * 1000, 4)
    assert any(b["accuracy"] == 1.0 for b in m["calibration"])
    assert m["n"] == 2 and m["errors"] == 0


def test_missed_incident_counted_and_unsafe_rate_undefined_without_autos():
    r = _rec("data_corruption", "escalate", False, "OBSERVE", True, True)
    r["incident_id"] = "INC-0011"
    m = compute_metrics([r])
    a = m["autonomy"]
    assert a["missed_incidents"] == 1 and a["missed_incident_ids"] == ["INC-0011"]
    assert a["auto"] == 0
    assert a["unsafe_auto_rate_pct"] is None      # undefined, not a reassuring 0
    assert a["escalation_recall_pct"] == 0


def test_errors_excluded_and_no_answers_gives_none():
    r = {"incident_id": "x", "archetype": "bad_deploy", "error": "boom", "latency_ms": 0,
         "decision": {"outcome": "ESCALATE"}, "ground_truth": {}}
    m = compute_metrics([r])
    assert m["errors"] == 1 and m["n_answered"] == 0
    assert m["decision_quality_pct"]["failure_category"] is None
    assert m["autonomy"]["auto_rate_pct"] is None and m["latency_ms"]["p50"] is None


def test_wilson_bounds():
    from zeroops.metrics import wilson
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and 40 < hi < 46     # 0 of 5 unsafe templates: upper bound ~43%
    assert wilson(0, 0) is None
