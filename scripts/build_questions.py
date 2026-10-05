#!/usr/bin/env python3
"""Render the considerations / questions document from its template and the results.

  ./jev/bin/python scripts/build_questions.py

inputs/questions.template.md holds the text, with {{placeholders}} for every number that
comes from the demo. This script fills them from work/results/facts.json and the decision logs
and writes outputs/3_open-questions-and-next-steps.md. An unknown or unused placeholder is an error, so the document
cannot silently drift from the results.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops.corpus import generate_corpus  # noqa: E402
from zeroops.paths import FACTS, QUESTIONS as OUT, QUESTIONS_TEMPLATE as TEMPLATE, decisions, rel  # noqa: E402
from zeroops.schema import REMEDIATION_ACTIONS  # noqa: E402

_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
          "eleven", "twelve"]


def words(n: int) -> str:
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def join_or(items: list[str]) -> str:
    items = list(items)
    if not items:
        return "none"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def join_and(items: list[str]) -> str:
    items = list(items)
    if not items:
        return "none"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def values() -> dict[str, str]:
    facts = json.loads(FACTS.read_text())
    j, b = facts["jev"], facts["backends"]
    jn = b["jev_native"]
    recs = [json.loads(line) for line in
            decisions("jev_native").read_text().splitlines() if line.strip()]
    autos = [r for r in recs if r["decision"]["outcome"] == "AUTO"]

    # incident length (whole alert text, words)
    wc = [len(i.state.split()) for i in generate_corpus(n_variants=4)]

    # calibration buckets as "0.6-0.7: 2/6" etc.
    calib = "; ".join(f"{c['bucket']}: {c['correct']} of {c['n']} right" for c in jn["calibration"])

    sens = {s["thresholds"]["page_min"]: s["auto"] for s in j["sensitivity"]}
    near = j["autos_near_page_cutoff"]
    dc = j["data_corruption"]
    first = j["first_listed_action"]
    ratio = round(j["first_option_proposed"] / j["first_option_labelled"]) if j["first_option_labelled"] else 0

    labelled = facts["labelled_actions"]
    never = [a for a in REMEDIATION_ACTIONS
             if labelled.get(a, 0) > 0 and j["proposed_actions"].get(a, 0) == 0]

    ranked = sorted(dc["stopped_by"].items(), key=lambda kv: -kv[1])
    stopped = [f"the {k} stopped {words(v)}" if i == 0 else f"the {k} {words(v)}"
               for i, (k, v) in enumerate(ranked)]
    n_rb = dc["proposed"].get("rollback", 0)
    dc_rollback_phrase = (f"all {words(dc['n'])}" if n_rb == dc["n"]
                          else f"{words(n_rb)} of the {words(dc['n'])}")

    wrong = Counter((r["archetype"].replace("_", " "), r["pred"]["proposed_action"].replace("_", " "))
                    for r in autos if not r["correct"]["action"])
    wrong_txt = join_and([f"{act} for {arch}" for (arch, act), _ in wrong.most_common()])

    ex = j["examples"]["auto"]
    cost = jn["cost_per_1k_usd"]

    return {
        "corpus_version": facts["corpus_version"],
        "n": str(facts["n"]),
        "n_templates": str(facts["n_templates"]),
        "words_min": str(min(wc)), "words_median": str(round(statistics.median(wc))), "words_max": str(max(wc)),
        "rc_jev_pct": f"{jn['root_cause']['pct']:.0f}%",
        "rc_kev_pct": f"{b['kev']['root_cause']['pct']:.0f}%" if "kev" in b else "n/a",
        "calib_list": calib,
        "top_k": str(j["category_conf_ge_0_9"]["correct"]), "top_n": str(j["category_conf_ge_0_9"]["n"]),
        "top_conf": f"{j['category_conf_ge_0_9']['mean_conf']:.2f}",
        "ece": f"{jn['calibration_ece']:.2f}",
        "page_cutoff": f"{near['cutoff']:.2f}",
        "autos": str(jn["auto"]), "autos_080": str(sens.get(0.8)), "autos_085": str(sens.get(0.85)),
        "near_k": str(near["k"]), "near_min": f"{near['min']:.2f}", "near_max": f"{near['max']:.2f}",
        "autos_max_page": f"{max(r['pred']['needs_page'] for r in autos):.2f}" if autos else "n/a",
        "first_opt": first, "first_prop": str(j["first_option_proposed"]), "first_lab": str(j["first_option_labelled"]),
        "first_ratio_words": words(ratio),
        "dc_rollback_phrase": dc_rollback_phrase,
        "dc_sev_min": f"{dc['severity_range'][0]:.2f}", "dc_sev_max": f"{dc['severity_range'][1]:.2f}",
        "dc_stopped": join_and(stopped),
        "never_chosen": join_or(a.replace("_", " ") for a in never),
        "suspect_pct": f"{jn['suspect']['pct']:.0f}%",
        "p50": f"{jn['p50_ms']:.0f}", "p95": f"{jn['p95_ms']:.0f}",
        "cost_1k": f"${cost:.3f}", "cost_1k_round": f"${cost:.2f}", "cost_5k": f"${cost * 5:.2f}",
        "mean_tokens": f"{jn['mean_input_tokens']:,.0f}",
        "kev_cat": f"{b['kev']['category']['pct']:.0f}%" if "kev" in b else "n/a",
        "laya_cat": f"{b['laya_local']['category']['pct']:.0f}%" if "laya_local" in b else "n/a",
        "escalated": str(jn["escalate"]),
        "autos_wrong": str(jn["auto"] - jn["auto_exact"]), "autos_wrong_examples": wrong_txt,
        "exact_pct": f"{jn['action_exact']['pct']:.0f}%", "acceptable_pct": f"{jn['action_acceptable']['pct']:.0f}%",
        "unsafe_t": str(jn["unsafe_templates"]), "unsafe_upper": f"{jn['unsafe_templates_upper95_pct']:.0f}%",
        "ex_id": ex["id"] if ex else "n/a",
        "ex_page_pct": f"{round(100 * ex['pred']['needs_page'])}%" if ex else "n/a",
        "jev_model": jn["model"],
        "or_model": b["jev_openrouter"]["model"] if "jev_openrouter" in b else "n/a",
    }


def render(template: str, vals: dict[str, str]) -> str:
    used = set(re.findall(r"\{\{(\w+)\}\}", template))
    unknown = used - set(vals)
    if unknown:
        raise SystemExit(f"unknown placeholders in template: {sorted(unknown)}")
    unused = set(vals) - used
    if unused:
        raise SystemExit(f"values computed but never used in the template: {sorted(unused)}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: vals[m.group(1)], template)


def main() -> int:
    out = render(TEMPLATE.read_text(), values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out)
    print(f"saved -> {rel(OUT)} ({len(out.split())} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
