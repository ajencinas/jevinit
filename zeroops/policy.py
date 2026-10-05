"""Confidence-gated ZeroOps policy — the code that owns the decision.

Jev supplies typed answers with probabilities; this module decides whether to act. The
thresholds are explicit, auditable numbers, not prompt text.

Provenance of the thresholds: they were set by hand before the first evaluation run
(policy.py predates every results file) and have never been validated on held-out data.
On the 56-incident demo corpus the automation rate is very sensitive to `page_min`
(see outputs/7_results-report.md and the Threshold Lab), so treat them as illustrative.

Order of checks (first match wins):
  0. any gating answer missing or malformed -> ESCALATE   (fail closed)
  1. model proposes "escalate"              -> ESCALATE   (a human-needed signal wins)
  2. needs_page >= page_min                 -> ESCALATE
  3. real_incident < real_incident_min      -> OBSERVE
  4. action not in AUTO_ACTIONS / low action confidence / high risk / high severity -> ESCALATE
  5. rollback only: deploy correlation and rollback safety must both clear their bars
  6. otherwise                              -> AUTO
Steps 1 and 2 come before step 3 so that a low "is this real?" score can no longer
override the model's own request for a human (Kev-4B logged four data-corruption incidents
as noise this way in the first run).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Parsed

OBSERVE, AUTO, ESCALATE = "OBSERVE", "AUTO", "ESCALATE"

# Actions a ZeroOps agent is ever allowed to take without a human.
AUTO_ACTIONS = {"rollback", "patch_config", "restart", "scale_up"}

# Answers the gate reads. If any is missing the gate cannot be evaluated, so it escalates.
GATING_QUESTIONS = (
    "real_incident", "needs_page", "proposed_action", "action_risk", "severity",
    "deploy_correlated", "safe_to_autorollback",
)

DEFAULT_THRESHOLDS: dict[str, float] = {
    "real_incident_min": 0.50,     # below this: not an incident
    "page_min": 0.90,              # a "page a human" probability at or above this escalates
    "action_conf_min": 0.60,       # min confidence in the chosen action to auto-run
    "rollback_deploy_corr_min": 0.80,
    "rollback_safe_min": 0.70,     # reversible-rollback safety bar
    "risk_max": 1.0,               # action_risk score 0..2 (low/medium/high); <= 1.0 passes,
                                   # so a "medium" risk action can still auto-run
    "severity_auto_max": 2.5,      # severity score 0..3; above this (towards SEV1) escalates
}


@dataclass
class PolicyDecision:
    outcome: str
    action: str
    rationale: str
    gates: dict[str, float] = field(default_factory=dict)

    @property
    def automates(self) -> bool:
        return self.outcome == AUTO


def _gates(p: Parsed) -> dict[str, float]:
    return {
        "real_incident": round(p.real_incident, 3),
        "needs_page": round(p.needs_page, 3),
        "action_conf": round(p.proposed_action_confidence, 3),
        "deploy_correlated": round(p.deploy_correlated, 3),
        "safe_to_autorollback": round(p.safe_to_autorollback, 3),
        "action_risk": round(p.action_risk, 3),
        "severity": round(p.severity, 2),
    }


def decide(p: Parsed, th: dict[str, float] | None = None) -> PolicyDecision:
    t = {**DEFAULT_THRESHOLDS, **(th or {})}
    g = _gates(p)

    # 0. fail closed: the gate cannot be evaluated on missing answers
    missing = [q for q in GATING_QUESTIONS if q in (p.missing or [])]
    if missing:
        return PolicyDecision(ESCALATE, "escalate",
                              f"missing or malformed answers: {', '.join(missing)} (fail closed)", g)

    # 1-2. any human-needed signal wins over "not an incident"
    if p.proposed_action == "escalate":
        return PolicyDecision(ESCALATE, "escalate", "model proposes escalate", g)
    if p.needs_page >= t["page_min"]:
        return PolicyDecision(ESCALATE, "escalate",
                              f"needs_page={g['needs_page']} >= {t['page_min']}", g)

    # 3. not an incident -> observe
    if p.real_incident < t["real_incident_min"]:
        return PolicyDecision(OBSERVE, "observe",
                              f"real_incident={g['real_incident']} < {t['real_incident_min']}", g)

    # 4. general action gates
    if p.proposed_action not in AUTO_ACTIONS:
        return PolicyDecision(ESCALATE, p.proposed_action or "escalate",
                              f"action '{p.proposed_action}' is not in the auto-approved set", g)
    if p.proposed_action_confidence < t["action_conf_min"]:
        return PolicyDecision(ESCALATE, p.proposed_action,
                              f"action confidence {g['action_conf']} < {t['action_conf_min']}", g)
    if p.action_risk > t["risk_max"]:
        return PolicyDecision(ESCALATE, p.proposed_action,
                              f"action_risk {g['action_risk']} > {t['risk_max']}", g)
    if p.severity > t["severity_auto_max"]:
        return PolicyDecision(ESCALATE, p.proposed_action,
                              f"severity {g['severity']} > {t['severity_auto_max']} (page)", g)

    # 5. rollback-specific gate
    if p.proposed_action == "rollback":
        if (p.deploy_correlated >= t["rollback_deploy_corr_min"]
                and p.safe_to_autorollback >= t["rollback_safe_min"]):
            return PolicyDecision(AUTO, "rollback",
                                  f"deploy_correlated={g['deploy_correlated']} & "
                                  f"safe_to_autorollback={g['safe_to_autorollback']} clear the rollback gate", g)
        return PolicyDecision(ESCALATE, "rollback",
                              "rollback gate not cleared (deploy correlation or safety low)", g)

    # 6. restart/scale_up/patch_config: confidence, risk and severity already checked
    return PolicyDecision(AUTO, p.proposed_action,
                          f"{p.proposed_action} is auto-approved at action_conf={g['action_conf']} "
                          f"risk={g['action_risk']}", g)


def explain(p: Parsed, th: dict[str, float] | None = None) -> list[dict]:
    """Evaluate every numeric gate check (not short-circuited) for display.

    Returns rows {check, value, op, threshold, passed, margin} in policy order. `margin` is
    signed: positive = how far the value clears the threshold, negative = how far it misses.
    The rollback rows are included only when the proposed action is rollback. Builders use
    this so slides and pages show real PASS/FAIL values instead of hand-typed ones.
    """
    t = {**DEFAULT_THRESHOLDS, **(th or {})}
    rows = [
        ("needs_page", p.needs_page, "<", t["page_min"]),
        ("real_incident", p.real_incident, ">=", t["real_incident_min"]),
        ("action_conf", p.proposed_action_confidence, ">=", t["action_conf_min"]),
        ("action_risk", p.action_risk, "<=", t["risk_max"]),
        ("severity", p.severity, "<=", t["severity_auto_max"]),
    ]
    if p.proposed_action == "rollback":
        rows += [
            ("deploy_correlated", p.deploy_correlated, ">=", t["rollback_deploy_corr_min"]),
            ("safe_to_autorollback", p.safe_to_autorollback, ">=", t["rollback_safe_min"]),
        ]
    out = []
    for name, v, op, thr in rows:
        if op == "<":
            passed, margin = v < thr, thr - v
        elif op == "<=":
            passed, margin = v <= thr, thr - v
        else:
            passed, margin = v >= thr, v - thr
        out.append({"check": name, "value": round(v, 3), "op": op, "threshold": thr,
                    "passed": bool(passed), "margin": round(margin, 3)})
    return out
