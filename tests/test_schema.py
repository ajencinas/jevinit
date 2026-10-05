from zeroops.schema import (
    ACCEPTABLE_ACTIONS, REMEDIATION_ACTIONS, ROOT_CAUSES, SERVICES,
    incident_questions, parse_answers,
)


def test_question_set_shape():
    q = incident_questions()
    assert len(q) == 12
    types = {v["type"] for v in q.values()}
    assert types == {"noul", "choice", "score"}
    for name, spec in q.items():
        if spec["type"] == "choice":
            assert isinstance(spec["criteria"], dict) and spec["criteria"]
        if spec["type"] == "score":
            assert isinstance(spec["criteria"], list) and spec["criteria"]
        assert spec.get("instructions")


def test_parse_answers_flat_record():
    raw = {
        "real_incident": {"type": "noul", "noul": 0.94},
        "failure_category": {"type": "choice", "choice": "config", "confidence": 1.0,
                             "probabilities": {"config": 1.0}},
        "suspect_component": {"type": "choice", "choice": "payment-svc", "confidence": 0.7},
        "root_cause": {"type": "choice", "choice": "bad_deploy", "confidence": 0.9},
        "deploy_correlated": {"type": "noul", "noul": 0.9},
        "severity": {"type": "score", "score": 2.3, "confidence": 0.7},
        "blast_radius": {"type": "score", "score": 1.0},
        "customer_impact": {"type": "noul", "noul": 0.8},
        "safe_to_autorollback": {"type": "noul", "noul": 0.74},
        "proposed_action": {"type": "choice", "choice": "rollback", "confidence": 0.95},
        "action_risk": {"type": "score", "score": 0.1},
        "needs_page": {"type": "noul", "noul": 0.6},
    }
    p = parse_answers(raw)
    assert p.real_incident == 0.94
    assert p.failure_category == "config"
    assert p.proposed_action == "rollback"
    assert p.severity == 2.3
    assert p.failure_category_probs == {"config": 1.0}


def test_parse_answers_records_missing():
    p = parse_answers({})
    # values still default for display, but every question is flagged as missing
    assert p.real_incident == 0.0 and p.failure_category == ""
    assert set(p.missing) == set(incident_questions())


def test_parse_answers_flags_malformed_values():
    raw = {
        "real_incident": {"type": "noul", "noul": "high"},          # not a number
        "proposed_action": {"type": "choice", "choice": "reboot"},  # not an allowed option
        "severity": {"type": "score", "score": None},
    }
    p = parse_answers(raw)
    assert {"real_incident", "proposed_action", "severity"} <= set(p.missing)
    assert p.real_incident == 0.0


def test_missing_answers_escalate_instead_of_observe():
    from zeroops.policy import ESCALATE, decide
    d = decide(parse_answers({}))
    assert d.outcome == ESCALATE and "fail closed" in d.rationale


def test_acceptable_actions_cover_archetypes():
    from zeroops.corpus import generate_corpus
    archetypes = {i.archetype for i in generate_corpus(n_variants=1)}
    assert archetypes <= set(ACCEPTABLE_ACTIONS)
    for acts in ACCEPTABLE_ACTIONS.values():
        assert acts <= set(REMEDIATION_ACTIONS)


def test_taxonomies_have_core_entries():
    assert {"checkout-api", "payment-svc"} <= set(SERVICES)
    assert "bad_deploy" in ROOT_CAUSES and "security_incident" in ROOT_CAUSES
