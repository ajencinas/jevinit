"""Run one incident through an adapter + the confidence-gated policy."""
from __future__ import annotations

from .adapters import SystemOneAdapter
from .corpus import Incident
from .policy import DEFAULT_THRESHOLDS, ESCALATE, PolicyDecision, decide


def run_incident(adapter: SystemOneAdapter, inc: Incident,
                 thresholds: dict | None = None, corpus_version: str = "") -> dict:
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    result = adapter.decide(inc.state)
    gt = inc.ground_truth
    base = {
        "incident_id": inc.id, "archetype": inc.archetype, "backend": adapter.name,
        "corpus_version": corpus_version, "thresholds": th, "state": inc.state,
    }
    if not result.ok:
        # fail closed: a backend error means a person looks at it
        return {
            **base,
            "error": result.error, "latency_ms": result.latency_ms, "attempts": result.attempts,
            "decision": {"outcome": ESCALATE, "action": "escalate",
                         "rationale": "backend error (fail closed)", "gates": {}},
            "ground_truth": gt,
        }

    p = result.parsed
    decision: PolicyDecision = decide(p, th)

    return {
        **base,
        "model": result.model,
        "provider": result.provider,
        "latency_ms": round(result.latency_ms, 1),
        "attempts": result.attempts,
        "cost_usd": result.cost_usd,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        # prediction
        "pred": {
            "real_incident": p.real_incident,
            "failure_category": p.failure_category,
            "category_confidence": p.failure_category_confidence,
            "category_probs": p.failure_category_probs,
            "suspect_component": p.suspect_component,
            "root_cause": p.root_cause,
            "deploy_correlated": p.deploy_correlated,
            "severity": p.severity,
            "severity_confidence": p.severity_confidence,
            "blast_radius": p.blast_radius,
            "customer_impact": p.customer_impact,
            "safe_to_autorollback": p.safe_to_autorollback,
            "proposed_action": p.proposed_action,
            "action_confidence": p.proposed_action_confidence,
            "action_probs": p.proposed_action_probs,
            "action_risk": p.action_risk,
            "needs_page": p.needs_page,
            "missing": p.missing,
        },
        # policy
        "decision": {
            "outcome": decision.outcome,
            "action": decision.action,
            "rationale": decision.rationale,
            "gates": decision.gates,
        },
        "ground_truth": gt,
        "correct": {
            "real_incident": (p.real_incident >= th["real_incident_min"]) == gt["real_incident"],
            "failure_category": p.failure_category == gt["failure_category"],
            "suspect_component": p.suspect_component == gt["suspect_component"],
            "root_cause": p.root_cause == gt["root_cause"],
            "action": p.proposed_action == gt["correct_action"],
            "severity_abs_err": round(abs(p.severity - gt["severity"]), 2),
        },
        "error": None,
    }
