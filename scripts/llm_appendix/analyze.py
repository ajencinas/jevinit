#!/usr/bin/env python3
"""Score every backend from the appendix decision logs; writes the scorecard JSON and CSV tables.

  ./jev/bin/python scripts/llm_appendix/analyze.py

No API calls. Reads work/results/llm_appendix/*.jsonl, writes work/results/llm_appendix/scorecard.json and
outputs/appendix-jev-vs-llms/data/*.csv. Confidence for the action question is the probability of the chosen
option: Jev's own distribution, the LLM's stated probability, and for Qwen also its token probabilities.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE)]
from zeroops import paths  # noqa: E402
from zeroops import llm_appendix_paths as loc  # noqa: E402
from zeroops.facts import parsed_from_pred, reason_kind  # noqa: E402
from zeroops.metrics import compute_metrics, wilson  # noqa: E402
from zeroops.policy import DEFAULT_THRESHOLDS, decide  # noqa: E402
from run import BACKENDS, JEV, JEV_PRICE_IN, MODELS, RUNS  # noqa: E402

LABELS = {JEV: "Jev 1.13 (TypeSafe API)", "claude-sonnet-5.5": "Claude Sonnet 5.5", "gpt-6.1-sol": "GPT-6.1 Sol",
          "gemini-3.8-flash": "Gemini 3.8 Flash", "gpt-6-luna": "GPT-6 Luna", "qwen3.8-flash": "Qwen3.8 Flash"}
TOKEN_PROBS = "qwen3.8-flash"          # the one endpoint that returns token log probabilities
COVERAGE = (0.25, 0.5, 0.75, 1.0)


def load(backend: str, condition: str, run: int) -> list[dict]:
    path = loc.RESULTS / loc.log(backend, condition, run).name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ok(recs: list[dict]) -> list[dict]:
    return [r for r in recs if not r.get("error") and "pred" in r]


def action_conf(r: dict, source: str = "stated") -> float | None:
    """Probability of the chosen action: Jev's distribution, the stated probability, or token probabilities."""
    action = r["pred"]["proposed_action"]
    if r["backend"] == JEV:
        return (r["pred"].get("action_probs") or {}).get(action)
    llm = r.get("llm") or {}
    if source == "tokens":
        return ((llm.get("logprob_probs") or {}).get("proposed_action") or {}).get(action)
    return (llm.get("stated") or {}).get("proposed_action")


def confidence_quality(pairs: list[tuple[float, bool]]) -> dict:
    """ECE (10 bins), Brier score, AUROC and accuracy among the most confident answers (ties shared out)."""
    if not pairs:
        return {}
    n = len(pairs)
    bins: dict[int, list] = {}
    for c, y in pairs:
        bins.setdefault(min(9, int(c * 10)), []).append((c, y))
    ece = sum(abs(statistics.fmean(c for c, _ in b) - statistics.fmean(y for _, y in b)) * len(b)
              for b in bins.values()) / n
    brier = statistics.fmean((c - y) ** 2 for c, y in pairs)
    area = auroc([c for c, y in pairs if y], [c for c, y in pairs if not y])
    # selective accuracy: answers ranked by confidence; a tie group counts at its mean accuracy
    groups: dict[float, list[bool]] = {}
    for c, y in pairs:
        groups.setdefault(round(c, 6), []).append(y)
    ranked = sorted(groups.items(), key=lambda kv: -kv[0])
    selective = {}
    for cov in COVERAGE:
        want, got, hits = cov * n, 0.0, 0.0
        for _, ys in ranked:
            take = min(len(ys), want - got)
            if take <= 0:
                break
            hits += take * statistics.fmean(ys)
            got += take
        selective[f"{int(cov * 100)}"] = round(100 * hits / got, 1) if got else None
    return {"n": n, "ece": round(ece, 3), "brier": round(brier, 3),
            "auroc": area, "selective_accuracy_pct": selective,
            "distinct_values": len(groups), "mean_conf": round(statistics.fmean(c for c, _ in pairs), 3),
            "accuracy_pct": round(100 * statistics.fmean(y for _, y in pairs), 1)}


def gate_counts(recs: list[dict], th: dict | None = None) -> dict:
    out = Counter()
    for r in ok(recs):
        d = decide(parsed_from_pred(r["pred"]), {**DEFAULT_THRESHOLDS, **(th or {})})
        if d.outcome == "AUTO":
            out["auto"] += 1
            out["unsafe"] += not r["ground_truth"]["auto_safe"]
            out["wrong"] += d.action != r["ground_truth"]["correct_action"]
    return dict(out)


def best_thresholds(recs: list[dict]) -> dict:
    """Most AUTO decisions with none unsafe and none wrong, over a grid of the page and action-confidence
    cut-offs. Fitted on the same 56 incidents, so it is a ceiling, not a forecast."""
    best = {"auto": 0, "page_min": None, "action_conf_min": None}
    for page in [x / 100 for x in range(5, 100, 5)] + [0.99, 1.0]:
        for conf in [x / 20 for x in range(0, 20)]:
            c = gate_counts(recs, {"page_min": page, "action_conf_min": conf})
            if c.get("unsafe", 0) == 0 and c.get("wrong", 0) == 0 and c.get("auto", 0) > best["auto"]:
                best = {"auto": c["auto"], "page_min": page, "action_conf_min": conf}
    return best


def held_out(recs: list[dict]) -> dict:
    """Leave one scenario type out: fit the cut-offs on 13 types, apply them to the 4 incidents of the 14th."""
    out = Counter()
    types = sorted({r["archetype"] for r in ok(recs)})
    for t in types:
        fit = best_thresholds([r for r in recs if r["archetype"] != t])
        if fit["page_min"] is None:
            continue
        c = gate_counts([r for r in recs if r["archetype"] == t],
                        {"page_min": fit["page_min"], "action_conf_min": fit["action_conf_min"]})
        out.update(c)
    return {"auto": out["auto"], "unsafe": out["unsafe"], "wrong": out["wrong"], "folds": len(types)}


def auroc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    return round(sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg)), 3)


def same_across(runs: list[list[dict]], key) -> float | None:
    by_id = [{r["incident_id"]: key(r) for r in ok(rs)} for rs in runs]
    ids = set.intersection(*(set(b) for b in by_id)) if by_id else set()
    if not ids:
        return None
    return round(100 * sum(len({b[i] for b in by_id}) == 1 for i in ids) / len(ids), 1)


def summarise(backend: str) -> dict | None:
    runs = {(c, r): load(backend, c, r) for c, r in RUNS}
    base = runs[("base", 1)]
    if not base:
        return None
    m = compute_metrics(base)
    base3 = [rec for r in (1, 2, 3) for rec in ok(runs[("base", r)])]
    every = [rec for rs in runs.values() for rec in rs]

    def answered(rs):
        return ok(rs)

    def acc(rs, field):
        o = answered(rs)
        return round(100 * sum(bool(r["correct"][field]) for r in o) / len(o), 1) if o else None

    # cost per call: billed for the LLMs; list-price estimate for Jev (the TypeSafe API returns no cost)
    if backend == JEV:
        tokens = [r["input_tokens"] for r in answered(every)]
        per_call = statistics.fmean(tokens) * JEV_PRICE_IN / 1e6 if tokens else None
        cost_basis = "list-price estimate"
    else:
        costs = [r["cost_usd"] for r in answered(every) if r.get("cost_usd") is not None]
        per_call = statistics.fmean(costs) if costs else None
        cost_basis = "billed by OpenRouter"
    lat = sorted(r["latency_ms"] for r in base3)
    conf_pairs = [(c, bool(r["correct"]["action"])) for r in base3 if (c := action_conf(r)) is not None]
    out = {
        "backend": backend, "label": LABELS[backend],
        "model": next((r.get("model") for r in answered(every) if r.get("model")), ""),
        "providers": sorted({r.get("provider") or "" for r in answered(every)} - {""}),
        "settings": ({} if backend == JEV else
                     {k: next((r["llm"].get(k) for r in answered(every) if r.get("llm")), None)
                      for k in ("reasoning", "temperature")}),
        # every distinct (reasoning, temperature) seen; more than one would mean a setting changed mid-run
        "settings_seen": sorted({json.dumps([(r.get("llm") or {}).get("reasoning"),
                                             (r.get("llm") or {}).get("temperature")]) for r in answered(every)}),
        "calls": len(every), "errors": sum(bool(r.get("error")) for r in every),
        "schema_valid_pct": round(100 * sum(not r["pred"]["missing"] for r in answered(every)) / max(1, len(answered(every))), 1),
        "accuracy_pct": m["decision_quality_pct"],
        "counts": m["counts"], "ci95": m["ci95_pct"],
        "gate": {k: m["autonomy"][k] for k in ("auto", "escalate", "observe", "auto_strict_correct", "auto_precision_pct",
                                               "unsafe_auto", "missed_incidents", "escalated_non_incidents")},
        "gate_reasons": dict(Counter(reason_kind(r["decision"]["rationale"]) for r in answered(base))),
        "needs_page_mean": round(statistics.fmean(r["pred"]["needs_page"] for r in answered(base)), 3),
        "best_thresholds": best_thresholds(base),
        "held_out": held_out(base),
        # does P(page) rank the unsafe incidents above the real, safe ones (the cases the gate must tell apart)
        "page_auroc": auroc([r["pred"]["needs_page"] for r in answered(base) if not r["ground_truth"]["auto_safe"]],
                            [r["pred"]["needs_page"] for r in answered(base)
                             if r["ground_truth"]["auto_safe"] and r["ground_truth"]["real_incident"]]),
        "confidence": confidence_quality(conf_pairs),
        "latency_ms": {"p50": round(statistics.median(lat), 1) if lat else None,
                       "p95": round(lat[max(0, int(0.95 * len(lat) + 0.999) - 1)], 1) if lat else None},
        "cost": {"per_call_usd": per_call, "per_1k_usd": round(per_call * 1000, 4) if per_call else None,
                 "basis": cost_basis,
                 "billed_total_usd": round(sum(r.get("cost_usd") or 0 for r in every), 4)},
        "tokens": {"input_mean": round(statistics.fmean(r["input_tokens"] for r in answered(every))),
                   "output_mean": round(statistics.fmean(r["output_tokens"] for r in answered(every))),
                   "reasoning_mean": round(statistics.fmean((r.get("llm") or {}).get("reasoning_tokens") or 0
                                                            for r in answered(every)), 1)},
        "consistency_pct": {
            "action": same_across([runs[("base", r)] for r in (1, 2, 3)], lambda r: r["pred"]["proposed_action"]),
            "category": same_across([runs[("base", r)] for r in (1, 2, 3)], lambda r: r["pred"]["failure_category"]),
            "gate_outcome": same_across([runs[("base", r)] for r in (1, 2, 3)], lambda r: r["decision"]["outcome"]),
            "exact_action_by_run": [acc(runs[("base", r)], "action") for r in (1, 2, 3)],
            "auto_by_run": [compute_metrics(runs[("base", r)])["autonomy"]["auto"] if runs[("base", r)] else None
                            for r in (1, 2, 3)],
        },
    }
    if backend == TOKEN_PROBS:
        tok_pairs = [(c, bool(r["correct"]["action"])) for r in base3 if (c := action_conf(r, "tokens")) is not None]
        out["confidence_tokens"] = confidence_quality(tok_pairs)
    stress = {}
    base_by_id = {r["incident_id"]: r for r in answered(base)}
    for cond in ("shuffled", "injected", "harder"):
        rs = runs[(cond, 1)]
        if not rs:
            continue
        mc = compute_metrics(rs)
        o = answered(rs)
        changed = [r for r in o if r["incident_id"] in base_by_id
                   and r["pred"]["proposed_action"] != base_by_id[r["incident_id"]]["pred"]["proposed_action"]]
        stress[cond] = {
            "n": len(o),
            "accuracy_pct": {k: mc["decision_quality_pct"][k] for k in ("failure_category", "root_cause", "action",
                                                                        "action_acceptable")},
            "auto": mc["autonomy"]["auto"], "unsafe_auto": mc["autonomy"]["unsafe_auto"],
            "wrong_auto": mc["autonomy"]["auto"] - mc["autonomy"]["auto_strict_correct"],
            "action_changed_vs_base": len(changed),
            "rollback_proposed": sum(r["pred"]["proposed_action"] == "rollback" for r in o),
            "needs_page_mean": round(statistics.fmean(r["pred"]["needs_page"] for r in o), 3) if o else None,
            "page_dropped": sum(base_by_id[r["incident_id"]]["pred"]["needs_page"] - r["pred"]["needs_page"] >= 0.3
                                for r in o if r["incident_id"] in base_by_id),
            "best_thresholds_from_base": gate_counts(rs, {k: v for k, v in out["best_thresholds"].items()
                                                          if k != "auto" and v is not None}),
        }
    out["rollback_proposed_base"] = sum(r["pred"]["proposed_action"] == "rollback" for r in answered(base))
    out["stress"] = stress
    return out


def per_incident_rows(backend: str):
    for c, run in RUNS:
        for r in load(backend, c, run):
            p = r.get("pred") or {}
            yield {"backend": backend, "condition": c, "run": run, "incident": r["incident_id"],
                   "archetype": r["archetype"], "gold_action": r["ground_truth"]["correct_action"],
                   "auto_safe": r["ground_truth"]["auto_safe"], "action": p.get("proposed_action", ""),
                   "action_prob": action_conf(r) if p else "", "category": p.get("failure_category", ""),
                   "needs_page": p.get("needs_page", ""), "outcome": r["decision"]["outcome"],
                   "action_correct": (r.get("correct") or {}).get("action", ""), "latency_ms": r.get("latency_ms"),
                   "cost_usd": r.get("cost_usd"), "error": r.get("error") or ""}


def main() -> int:
    cards = [c for b in BACKENDS if (c := summarise(b))]
    if not cards:
        print(f"no decision logs in {paths.rel(loc.RESULTS)}; run scripts/llm_appendix/run.py first")
        return 1
    n_unsafe = sum(not r["ground_truth"]["auto_safe"] for r in load(cards[0]["backend"], "base", 1))
    scorecard = {"backends": cards, "n_incidents": 56, "n_unsafe": n_unsafe, "thresholds": DEFAULT_THRESHOLDS,
                 "runs": RUNS, "models": {b: m[0] for b, m in MODELS.items()},
                 "unsafe_ci_zero": wilson(0, n_unsafe)}
    loc.SCORECARD.write_text(json.dumps(scorecard, indent=1))
    loc.DATA.mkdir(parents=True, exist_ok=True)
    rows = [{"backend": c["label"], "exact_action_pct": c["accuracy_pct"]["action"],
             "acceptable_action_pct": c["accuracy_pct"]["action_acceptable"],
             "category_pct": c["accuracy_pct"]["failure_category"], "root_cause_pct": c["accuracy_pct"]["root_cause"],
             "component_pct": c["accuracy_pct"]["suspect_component"],
             "severity_within_1_pct": c["accuracy_pct"]["severity_within_1"],
             "auto": c["gate"]["auto"], "unsafe_auto": c["gate"]["unsafe_auto"],
             "wrong_auto": c["gate"]["auto"] - c["gate"]["auto_strict_correct"],
             "missed_incidents": c["gate"]["missed_incidents"], "best_auto_zero_wrong": c["best_thresholds"]["auto"],
             "held_out_auto": c["held_out"]["auto"], "held_out_unsafe": c["held_out"]["unsafe"],
             "held_out_wrong": c["held_out"]["wrong"], "page_auroc": c["page_auroc"],
             "action_ece": c["confidence"].get("ece"), "action_auroc": c["confidence"].get("auroc"),
             "same_action_3_runs_pct": c["consistency_pct"]["action"],
             "p50_ms": c["latency_ms"]["p50"], "p95_ms": c["latency_ms"]["p95"],
             "usd_per_1k": c["cost"]["per_1k_usd"], "cost_basis": c["cost"]["basis"]} for c in cards]
    with (loc.DATA / "scorecard.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (loc.DATA / "per_incident.csv").open("w", newline="") as fh:
        rows = [row for c in cards for row in per_incident_rows(c["backend"])]
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for c in cards:
        g = c["gate"]
        print(f"{c['label']:26} exact {c['accuracy_pct']['action']:5}%  AUTO {g['auto']:2} (unsafe {g['unsafe_auto']}) "
              f"best {c['best_thresholds']['auto']:2} held-out {c['held_out']}  ECE {c['confidence'].get('ece')}  "
              f"settings {c['settings_seen']} providers {c['providers']}  "
              f"p50 {c['latency_ms']['p50']} ms  ${c['cost']['per_1k_usd']}/1k")
    print(f"wrote {paths.rel(loc.SCORECARD)} and {paths.rel(loc.DATA)}/*.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
