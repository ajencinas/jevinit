"""Narrative facts computed from the decision logs — the single source for every number that
appears in the deck, memo, README, web pages and video scripts.

scripts/report.py writes the output to work/results/facts.json. Builders must read numbers from
there (or from work/results/metrics.json) instead of typing them in; the README rule "never
hardcode results" is enforced by tests/test_facts.py for the generated memo.
"""
from __future__ import annotations

from collections import Counter

from .metrics import wilson
from .policy import DEFAULT_THRESHOLDS, decide, explain
from .schema import ACCEPTABLE_ACTIONS, REMEDIATION_ACTIONS, Parsed

PRIMARY = "jev_native"
LABELS = {
    "jev_native": "Jev (TypeSafe API)",
    "jev_openrouter": "Jev (via OpenRouter)",
    "kev": "Kev-4B (local GPU)",
    "laya_local": "Laya (local GPU)",
}
ORDER = ["jev_native", "jev_openrouter", "kev", "laya_local"]
LOCAL = {"kev", "laya_local"}


def parsed_from_pred(pred: dict) -> Parsed:
    """Rebuild the policy input from a stored record's `pred` block."""
    return Parsed(
        real_incident=pred["real_incident"],
        failure_category=pred["failure_category"],
        failure_category_confidence=pred["category_confidence"],
        failure_category_probs=pred.get("category_probs") or {},
        suspect_component=pred["suspect_component"],
        root_cause=pred["root_cause"],
        deploy_correlated=pred["deploy_correlated"],
        severity=pred["severity"],
        severity_confidence=pred["severity_confidence"],
        blast_radius=pred["blast_radius"],
        customer_impact=pred["customer_impact"],
        safe_to_autorollback=pred["safe_to_autorollback"],
        proposed_action=pred["proposed_action"],
        proposed_action_confidence=pred["action_confidence"],
        proposed_action_probs=pred.get("action_probs") or {},
        action_risk=pred["action_risk"],
        needs_page=pred["needs_page"],
        missing=list(pred.get("missing") or []),
    )


_REASONS = [
    ("missing or malformed", "missing answers"),
    ("model proposes escalate", "model proposed escalate"),
    ("needs_page", "page-a-human check"),
    ("real_incident", "not-an-incident check"),
    ("not in the auto-approved set", "action not auto-approved"),
    ("action confidence", "action-confidence check"),
    ("action_risk", "risk check"),
    ("severity", "severity check"),
    ("rollback gate not cleared", "rollback checks"),
    ("clear the rollback gate", "auto (rollback checks passed)"),
    ("is auto-approved", "auto"),
    ("backend error", "backend error"),
]


def reason_kind(rationale: str) -> str:
    """Map a PolicyDecision rationale to a short, stable label."""
    for needle, label in _REASONS:
        if needle in rationale:
            return label
    return rationale


def _ok(recs: list[dict]) -> list[dict]:
    return [r for r in recs if not r.get("error") and "pred" in r]


def autos_at(recs: list[dict], **overrides: float) -> dict:
    """Re-run the gate over stored answers with some thresholds changed."""
    th = {**DEFAULT_THRESHOLDS, **overrides}
    out = [(r, decide(parsed_from_pred(r["pred"]), th).outcome) for r in _ok(recs)]
    auto = [r for r, o in out if o == "AUTO"]
    return {"thresholds": overrides, "auto": len(auto),
            "unsafe_auto": sum(not r["ground_truth"]["auto_safe"] for r in auto)}


def _example(r: dict) -> dict:
    p = parsed_from_pred(r["pred"])
    return {
        "id": r["incident_id"], "archetype": r["archetype"], "state": r["state"],
        "service": r["state"].split("service: ", 1)[1].split("\n", 1)[0] if "service: " in r["state"] else "",
        "latency_ms": r["latency_ms"],
        "pred": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r["pred"].items()
                 if k not in ("category_probs", "action_probs")},
        "ground_truth": r["ground_truth"],
        "outcome": r["decision"]["outcome"], "action": r["decision"]["action"],
        "rationale": r["decision"]["rationale"],
        "checks": explain(p, r.get("thresholds")),
    }


def backend_summary(name: str, recs: list[dict], m: dict) -> dict:
    ok = _ok(recs)
    a, c, q = m["autonomy"], m["counts"], m["decision_quality_pct"]
    unsafe_t, unsafe_t_auto = a["unsafe_templates"], a["unsafe_templates_automated"]
    ci = wilson(len(unsafe_t_auto), len(unsafe_t))
    return {
        "label": LABELS.get(name, name),
        "model": next((r.get("model") for r in ok if r.get("model")), ""),
        "n": m["n"], "errors": m["errors"], "n_answered": m["n_answered"],
        "category": {"k": c["failure_category"], "pct": q["failure_category"]},
        "root_cause": {"k": c["root_cause"], "pct": q["root_cause"]},
        "suspect": {"k": c["suspect_component"], "pct": q["suspect_component"]},
        "action_exact": {"k": c["action"], "pct": q["action"]},
        "action_acceptable": {"k": c["action_acceptable"], "pct": q["action_acceptable"]},
        "severity_within_1": {"k": c["severity_within_1"], "pct": q["severity_within_1"]},
        "auto": a["auto"], "escalate": a["escalate"], "observe": a["observe"],
        "auto_pct": a["auto_rate_pct"],
        "auto_exact": a["auto_strict_correct"],
        "unsafe_auto": a["unsafe_auto"],
        "unsafe_cases": a["unsafe_cases"],
        "unsafe_templates": len(unsafe_t),
        "unsafe_templates_automated": len(unsafe_t_auto),
        "unsafe_templates_upper95_pct": ci[1] if ci else None,
        "templates_automated": len(a["templates_automated"]),
        "missed_incidents": a["missed_incidents"],
        "missed_incident_ids": a["missed_incident_ids"],
        "escalated_non_incidents": a["escalated_non_incidents"],
        "p50_ms": m["latency_ms"]["p50"], "p95_ms": m["latency_ms"]["p95"],
        "cost_per_1k_usd": m["cost"]["per_1k_usd"], "cost_basis": m["cost"].get("basis", ""),
        "mean_input_tokens": m.get("mean_input_tokens"),
        "mean_output_tokens": m.get("mean_output_tokens"),
        "calibration": m["calibration"], "calibration_ece": m["calibration_ece"],
    }


def build_facts(per_backend: dict[str, list[dict]], metrics: dict[str, dict],
                corpus_version: str) -> dict:
    names = [n for n in ORDER if n in per_backend] + [n for n in per_backend if n not in ORDER]
    facts: dict = {
        "corpus_version": corpus_version,
        "thresholds": DEFAULT_THRESHOLDS,
        "backends": {n: backend_summary(n, per_backend[n], metrics[n]) for n in names},
    }
    any_recs = next(iter(per_backend.values()))
    facts["n"] = len(any_recs)
    facts["n_templates"] = len({r["archetype"] for r in any_recs})
    facts["n_real"] = sum(r["ground_truth"]["real_incident"] for r in any_recs)
    facts["n_unsafe"] = sum(not r["ground_truth"]["auto_safe"] for r in any_recs)
    facts["labelled_actions"] = dict(Counter(r["ground_truth"]["correct_action"] for r in any_recs))

    if PRIMARY not in per_backend:
        return facts
    recs = _ok(per_backend[PRIMARY])
    j: dict = {}

    # what it proposed, against our labels (option order = REMEDIATION_ACTIONS order)
    j["proposed_actions"] = dict(Counter(r["pred"]["proposed_action"] for r in recs))
    j["first_listed_action"] = next(iter(REMEDIATION_ACTIONS))
    first = j["first_listed_action"]
    j["first_option_proposed"] = j["proposed_actions"].get(first, 0)
    j["first_option_labelled"] = facts["labelled_actions"].get(first, 0)

    # credit that exists only because of the lenient list
    only_lenient = [r for r in recs if not r["correct"]["action"]
                    and r["pred"]["proposed_action"] in ACCEPTABLE_ACTIONS.get(r["archetype"], set())]
    j["lenient_only_incidents"] = len(only_lenient)
    j["lenient_only_templates"] = sorted({r["archetype"] for r in only_lenient})

    # the automated incidents and how close they were to the paging cut-off
    autos = [r for r in recs if r["decision"]["outcome"] == "AUTO"]
    page_min = DEFAULT_THRESHOLDS["page_min"]
    near = sorted(r["pred"]["needs_page"] for r in autos if 0.70 <= r["pred"]["needs_page"] < page_min)
    j["autos"] = len(autos)
    j["autos_by_template"] = dict(Counter(r["archetype"] for r in autos))
    j["autos_near_page_cutoff"] = {"k": len(near), "of": len(autos),
                                   "min": round(near[0], 2) if near else None,
                                   "max": round(near[-1], 2) if near else None,
                                   "band_low": 0.70, "cutoff": page_min}
    j["autos_min_margin"] = sorted(
        ({"id": r["incident_id"], "check": c["check"], "margin": c["margin"]}
         for r in autos for c in [min(explain(parsed_from_pred(r["pred"])), key=lambda x: x["margin"])]),
        key=lambda x: x["margin"])[:6]
    j["sensitivity"] = [autos_at(per_backend[PRIMARY], page_min=v) for v in (0.80, 0.85, 0.95)]
    j["sensitivity_no_severity_gate"] = autos_at(per_backend[PRIMARY], severity_auto_max=99.0)

    # data corruption: what it proposed and what stopped it
    dc = [r for r in recs if r["archetype"] == "data_corruption"]
    j["data_corruption"] = {
        "n": len(dc),
        "proposed": dict(Counter(r["pred"]["proposed_action"] for r in dc)),
        "outcomes": dict(Counter(r["decision"]["outcome"] for r in dc)),
        "severity_range": [round(min(r["pred"]["severity"] for r in dc), 2),
                           round(max(r["pred"]["severity"] for r in dc), 2)] if dc else None,
        "needs_page_range": [round(min(r["pred"]["needs_page"] for r in dc), 2),
                             round(max(r["pred"]["needs_page"] for r in dc), 2)] if dc else None,
        "labelled_severity": dc[0]["ground_truth"]["severity"] if dc else None,
        "stopped_by": dict(Counter(reason_kind(r["decision"]["rationale"]) for r in dc)),
    }

    # does "page a human" separate incidents that need one? (mean on safe vs unsafe real incidents)
    safe_real = [r["pred"]["needs_page"] for r in recs
                 if r["ground_truth"]["auto_safe"] and r["ground_truth"]["real_incident"]]
    unsafe_real = [r["pred"]["needs_page"] for r in recs if not r["ground_truth"]["auto_safe"]]
    j["needs_page_mean"] = {"safe_real": round(sum(safe_real) / len(safe_real), 2) if safe_real else None,
                            "unsafe": round(sum(unsafe_real) / len(unsafe_real), 2) if unsafe_real else None}

    # high-confidence bucket for failure category
    top = [r for r in recs if r["pred"]["category_confidence"] >= 0.9]
    j["category_conf_ge_0_9"] = {
        "n": len(top), "correct": sum(r["correct"]["failure_category"] for r in top),
        "mean_conf": round(sum(r["pred"]["category_confidence"] for r in top) / len(top), 3) if top else None,
    }

    # worked examples: first automated bad deploy, first data-corruption incident
    def first(pred) -> dict | None:
        r = next((r for r in sorted(recs, key=lambda r: r["incident_id"]) if pred(r)), None)
        return _example(r) if r else None

    j["examples"] = {
        "auto": first(lambda r: r["archetype"] == "bad_deploy" and r["decision"]["outcome"] == "AUTO"),
        "stopped": first(lambda r: r["archetype"] == "data_corruption"),
    }

    # the same model through two endpoints
    if "jev_openrouter" in per_backend:
        other = {r["incident_id"]: r for r in _ok(per_backend["jev_openrouter"])}
        pairs = [(r, other[r["incident_id"]]) for r in recs if r["incident_id"] in other]
        fields = ("real_incident", "needs_page", "action_confidence", "severity", "category_confidence")
        j["endpoints"] = {
            "n": len(pairs),
            "prob_differs": sum(any(abs(a["pred"][f] - b["pred"][f]) > 1e-9 for f in fields) for a, b in pairs),
            "choice_differs": sum(a["pred"]["proposed_action"] != b["pred"]["proposed_action"]
                                  or a["pred"]["failure_category"] != b["pred"]["failure_category"]
                                  for a, b in pairs),
            "outcome_differs": [a["incident_id"] for a, b in pairs
                                if a["decision"]["outcome"] != b["decision"]["outcome"]],
            "models": sorted({a.get("model", "") for a, _ in pairs} | {b.get("model", "") for _, b in pairs}),
        }
    facts["jev"] = j
    return facts
