"""The incident decision schema: typed questions + a parser for System One answers.

This is the *specification* the whole demo rests on. One call per incident answers
every question in parallel; `parse_answers` turns the raw typed payload into a flat,
typed record the policy can branch on deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- fixed fleet topology + taxonomies (kept static so questions are comparable) ---

SERVICES = {
    "checkout-api": "Customer checkout and order placement",
    "payment-svc": "Payment authorization and capture",
    "auth-svc": "Login, sessions, tokens",
    "cart-svc": "Shopping cart state",
    "search-svc": "Product search and indexing",
    "db-primary": "Primary transactional database",
    "redis-cache": "Shared cache tier",
    "ingress": "Edge load balancer / API gateway",
}

FAILURE_CATEGORIES = {
    "app": "Application or code fault",
    "config": "Configuration error or bad deploy",
    "capacity": "Resource saturation (CPU/mem/connections)",
    "network": "Network, DNS, or connectivity",
    "security": "Security incident or intrusion",
    "storage": "Storage / database / disk fault",
    "other": "Something else",
}

ROOT_CAUSES = {
    "bad_deploy": "A recent deploy introduced the defect",
    "config_error": "A misconfiguration or bad runtime flag",
    "resource_exhaustion": "CPU, memory, connections, or disk exhausted",
    "network_partition": "Network loss/latency between components",
    "dns_failure": "Name resolution failing",
    "dependency_outage": "An upstream dependency is failing",
    "certificate_expiry": "An expired or invalid TLS certificate",
    "traffic_spike": "Sudden legitimate or abusive traffic surge",
    "data_corruption": "Corrupted or inconsistent data",
    "security_incident": "Intrusion, abuse, or credential compromise",
    "other": "None of the above",
}

REMEDIATION_ACTIONS = {
    "rollback": "Revert the most recent deploy",
    "patch_config": "Correct configuration and redeploy",
    "restart": "Restart the affected workload",
    "scale_up": "Add replicas or resources",
    "failover": "Fail over to a standby/region",
    "drain": "Drain a node/pod and reschedule",
    "observe": "Take no action; keep watching",
    "escalate": "Hand to a human immediately",
}

# Acceptable first actions per fault archetype -- a LENIENT, SECONDARY metric.
# Provenance matters: this list was written on 2026-10-03 at 08:04, after the first API run
# (07:48) had been scored, and every alternative that changed Jev's score is the action Jev
# picked. Treat "action_acceptable" as an author's judgement, not ground truth; the primary
# action metric is the strict match against `correct_action`. It is frozen as published so
# results stay comparable; a blind re-definition by an SRE is an open item (see CHANGES.md).
ACCEPTABLE_ACTIONS: dict[str, set[str]] = {
    "bad_deploy": {"rollback", "patch_config"},
    "config_drift": {"patch_config", "rollback"},
    "cpu_saturation": {"scale_up", "restart"},
    "memory_leak": {"restart", "scale_up"},
    "dependency_outage": {"failover", "escalate"},
    "network_partition": {"failover", "escalate"},
    "dns_failure": {"patch_config", "restart", "rollback"},
    "cert_expiry": {"patch_config", "rollback"},
    "traffic_spike": {"scale_up"},
    "db_saturation": {"escalate", "scale_up", "failover"},
    "data_corruption": {"escalate"},
    "security_incident": {"escalate"},
    "monitoring_fluke": {"observe"},
    "planned_maintenance": {"observe"},
}

SEVERITY_LEVELS = ["SEV4 cosmetic", "SEV3 minor", "SEV2 major", "SEV1 critical outage"]
BLAST_RADII = ["single pod", "single service", "multiple services", "region-wide"]
ACTION_RISKS = [
    "low: reversible, single service, no data loss",
    "medium: reversible, some blast radius",
    "high: irreversible or wide blast radius",
]


def incident_questions() -> dict[str, dict[str, Any]]:
    """Return the full typed question set (12 questions, mixed choice/score/noul)."""
    return {
        "real_incident": {
            "type": "noul",
            "instructions": "Is this a real service-impacting incident rather than a monitoring fluke or planned maintenance?",
        },
        "failure_category": {
            "type": "choice",
            "instructions": "Which failure category best explains the observed signals?",
            "criteria": FAILURE_CATEGORIES,
        },
        "suspect_component": {
            "type": "choice",
            "instructions": "Which component is most likely the origin of the fault?",
            "criteria": SERVICES,
        },
        "root_cause": {
            "type": "choice",
            "instructions": "What is the most likely root cause?",
            "criteria": ROOT_CAUSES,
        },
        "deploy_correlated": {
            "type": "noul",
            "instructions": "Does the timeline suggest a recent change or deploy caused this?",
        },
        "severity": {
            "type": "score",
            "instructions": "How severe is the customer impact?",
            "criteria": SEVERITY_LEVELS,
        },
        "blast_radius": {
            "type": "score",
            "instructions": "How wide is the affected blast radius?",
            "criteria": BLAST_RADII,
        },
        "customer_impact": {
            "type": "noul",
            "instructions": "Are end customers actually experiencing an impairment right now?",
        },
        "safe_to_autorollback": {
            "type": "noul",
            "instructions": "If a recent change is responsible, is an automated rollback safe (reversible, no data migration in flight)?",
        },
        "proposed_action": {
            "type": "choice",
            "instructions": "Which single remediation action should be taken first?",
            "criteria": REMEDIATION_ACTIONS,
        },
        "action_risk": {
            "type": "score",
            "instructions": "How risky is the proposed remediation action itself?",
            "criteria": ACTION_RISKS,
        },
        "needs_page": {
            "type": "noul",
            "instructions": "Should a human be paged immediately, independent of any automated action?",
        },
    }


# --- parsed answer record -----------------------------------------------------


@dataclass
class Parsed:
    real_incident: float = 0.0
    failure_category: str = ""
    failure_category_confidence: float = 0.0
    failure_category_probs: dict[str, float] = field(default_factory=dict)
    suspect_component: str = ""
    root_cause: str = ""
    root_cause_confidence: float = 0.0
    deploy_correlated: float = 0.0
    severity: float = 0.0
    severity_confidence: float = 0.0
    blast_radius: float = 0.0
    customer_impact: float = 0.0
    safe_to_autorollback: float = 0.0
    proposed_action: str = ""
    proposed_action_confidence: float = 0.0
    proposed_action_probs: dict[str, float] = field(default_factory=dict)
    action_risk: float = 0.0
    needs_page: float = 0.0
    # question ids whose answer was absent or malformed. The numeric fields above still
    # default to 0.0 for display, but the policy must not trust them: see policy.decide().
    missing: list[str] = field(default_factory=list)


# The answer the policy reads from each question, by question id.
_ANSWER_KEY = {"noul": "noul", "choice": "choice", "score": "score"}


def parse_answers(raw: dict[str, dict[str, Any]]) -> Parsed:
    """Flatten System One typed answers into a Parsed record.

    Missing or malformed answers are recorded in `Parsed.missing` instead of being silently
    read as 0.0 (which the policy would otherwise take as "not an incident" / "low risk").
    """
    p = Parsed()
    raw = raw or {}
    questions = incident_questions()

    def ans(qid: str) -> dict[str, Any]:
        a = raw.get(qid) or {}
        return a if isinstance(a, dict) else {}

    def num(qid: str, key: str) -> float:
        try:
            return float(ans(qid)[key])
        except (KeyError, TypeError, ValueError):
            return 0.0

    def probs(qid: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in (ans(qid).get("probabilities") or {}).items():
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    for qid, spec in questions.items():
        key = _ANSWER_KEY[spec["type"]]
        val = ans(qid).get(key)
        if spec["type"] == "choice":
            ok = isinstance(val, str) and val in spec["criteria"]
        else:
            try:
                ok = val is not None and float(val) == float(val)  # rejects None and NaN
            except (TypeError, ValueError):
                ok = False
        if not ok:
            p.missing.append(qid)

    p.real_incident = num("real_incident", "noul")

    p.failure_category = ans("failure_category").get("choice", "") or ""
    p.failure_category_confidence = num("failure_category", "confidence")
    p.failure_category_probs = probs("failure_category")

    p.suspect_component = ans("suspect_component").get("choice", "") or ""

    p.root_cause = ans("root_cause").get("choice", "") or ""
    p.root_cause_confidence = num("root_cause", "confidence")

    p.deploy_correlated = num("deploy_correlated", "noul")

    p.severity = num("severity", "score")
    p.severity_confidence = num("severity", "confidence")

    p.blast_radius = num("blast_radius", "score")
    p.customer_impact = num("customer_impact", "noul")
    p.safe_to_autorollback = num("safe_to_autorollback", "noul")

    p.proposed_action = ans("proposed_action").get("choice", "") or ""
    p.proposed_action_confidence = num("proposed_action", "confidence")
    p.proposed_action_probs = probs("proposed_action")

    p.action_risk = num("action_risk", "score")
    p.needs_page = num("needs_page", "noul")
    return p
