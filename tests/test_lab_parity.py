"""The Threshold Lab's gate must reproduce zeroops.policy.decide.

The lab (scripts/build_lab.py -> outputs/lab/index.html) evaluates the gate in the browser from a
rule table embedded in work/results/lab_data.json. These tests check, on every recorded answer, on
random edge cases and across the slider ranges:
  1. the rule table (evaluated here with a direct port of the page's JS) matches policy.decide;
  2. the page's actual JS function gives the same outcomes (run with node; skipped if absent);
  3. the page and work/results/lab_data.json carry the same data, and it matches the decision logs.
If policy.py changes order or semantics, rebuild the lab and update RULES in build_lab.py.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from zeroops.paths import LAB_DATA, LAB_PAGE as LAB_HTML, decisions, rel
from zeroops.policy import AUTO_ACTIONS, DEFAULT_THRESHOLDS, decide
from zeroops.schema import Parsed


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(LAB_DATA.read_text())


def py_gate(r: dict, th: dict, rules: list[dict]) -> str:
    """Line-for-line port of gate() in the page (see build_lab.py TEMPLATE)."""
    for rule in rules:
        if rule.get("only_action") and r["action"] != rule["only_action"]:
            continue
        c = rule["if"]
        v = r[c["field"]]
        ref = th[c["th"]] if "th" in c else c.get("value")
        op = c["op"]
        if op == "true":
            hit = bool(v)
        elif op == "eq":
            hit = v == ref
        elif op == "not_in":
            hit = v not in ref
        elif op == "ge":
            hit = v >= ref
        elif op == "lt":
            hit = v < ref
        elif op == "gt":
            hit = v > ref
        else:
            raise AssertionError(f"unknown op {op}")
        if hit:
            return rule["outcome"]
    return "AUTO"


def to_parsed(r: dict) -> Parsed:
    return Parsed(
        real_incident=r["real"], needs_page=r["page"], proposed_action=r["action"],
        proposed_action_confidence=r["aconf"], action_risk=r["risk"],
        deploy_correlated=r["depc"], safe_to_autorollback=r["safe"], severity=r["sev"],
        missing=["needs_page"] if r["missing"] else [],
    )


def threshold_settings(data: dict, n_random: int = 150) -> list[dict]:
    """Defaults, every slider position one at a time, and random combinations."""
    grids = {}
    for s in data["sliders"]:
        k = round((s["max"] - s["min"]) / s["step"])
        grids[s["key"]] = [round(s["min"] + i * s["step"], 2) for i in range(k + 1)]
    out = [dict(data["defaults"])]
    for key, vals in grids.items():
        out += [{**data["defaults"], key: v} for v in vals]
    rng = random.Random(11)
    out += [{key: rng.choice(vals) for key, vals in grids.items()} for _ in range(n_random)]
    return out


def edge_records(th: dict, n: int = 3000) -> list[dict]:
    """Random records whose values sit on, just above and just below the thresholds."""
    rng = random.Random(5)
    actions = sorted(AUTO_ACTIONS) + ["escalate", "observe", "failover", "drain", ""]
    near = {"page": "page_min", "real": "real_incident_min", "aconf": "action_conf_min",
            "risk": "risk_max", "sev": "severity_auto_max", "depc": "rollback_deploy_corr_min",
            "safe": "rollback_safe_min"}
    span = {"risk": 2.0, "sev": 3.0}
    recs = []
    for _ in range(n):
        r = {"action": rng.choice(actions), "missing": rng.random() < 0.08}
        for f, key in near.items():
            t = th[key]
            r[f] = rng.choice([t, round(t - 0.01, 2), round(t + 0.01, 2),
                               round(rng.uniform(0, span.get(f, 1.0)), 2)])
        recs.append(r)
    return recs


def test_lab_defaults_and_actions_match_policy(data):
    assert data["defaults"] == DEFAULT_THRESHOLDS
    rule = next(r for r in data["rules"] if r["id"] == "action_not_auto")
    assert sorted(rule["if"]["value"]) == sorted(AUTO_ACTIONS)
    assert {s["key"] for s in data["sliders"]} == set(DEFAULT_THRESHOLDS)
    assert [r["id"] for r in data["rules"]][:4] == ["missing", "model_escalate", "page", "not_incident"]


def test_rule_table_matches_policy_on_recorded_answers(data):
    for th in threshold_settings(data):
        for name, recs in data["backends"].items():
            for r in recs:
                want = decide(to_parsed(r), th).outcome
                got = py_gate(r, th, data["rules"])
                assert got == want, (name, r["id"], th, got, want)


def test_rule_table_matches_policy_on_edge_cases(data):
    for th in threshold_settings(data, n_random=20)[:: 7]:
        for r in edge_records(th, n=600):
            assert py_gate(r, th, data["rules"]) == decide(to_parsed(r), th).outcome, (r, th)


def test_lab_data_matches_decision_logs(data):
    for name, recs in data["backends"].items():
        logged = {}
        for line in decisions(name).read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                logged[rec["incident_id"]] = rec["decision"]["outcome"]
        for r in recs:
            assert r["exp"] == logged[r["id"]], (name, r["id"])
            assert py_gate(r, data["defaults"], data["rules"]) == r["exp"], (name, r["id"])


def test_page_embeds_current_lab_data(data):
    html = LAB_HTML.read_text()
    m = re.search(r"const DATA = (\{.*?\});\nconst RULES", html, re.S)
    assert m, f"DATA block not found in {rel(LAB_HTML)}"
    assert json.loads(m.group(1)) == data, f"{rel(LAB_HTML)} is stale; run scripts/build_lab.py"


def _node() -> str | None:
    for cand in (os.environ.get("NODE"), shutil.which("node"),
                 "/media/alfonso/shared/jev_local/node22/bin/node"):
        if cand and Path(cand).exists():
            return cand
    return None


@pytest.mark.skipif(_node() is None, reason="node not available")
def test_page_js_gate_matches_policy(data, tmp_path):
    html = LAB_HTML.read_text()
    m = re.search(r"/\*__GATE_JS_START__\*/(.*?)/\*__GATE_JS_END__\*/", html, re.S)
    assert m, f"gate() markers not found in {rel(LAB_HTML)}"
    settings = threshold_settings(data, n_random=60)
    recs = [r for recs in data["backends"].values() for r in recs]
    edges = edge_records(data["defaults"], n=1500)
    (tmp_path / "in.json").write_text(json.dumps(
        {"rules": data["rules"], "settings": settings, "recs": recs, "edges": edges,
         "defaults": data["defaults"]}))
    script = m.group(1) + r"""
const fs = require("fs");
const I = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = {grid: I.settings.map(th => I.recs.map(r => gate(r, th, I.rules).outcome)),
             edges: I.edges.map(r => gate(r, I.defaults, I.rules).outcome)};
process.stdout.write(JSON.stringify(out));
"""
    (tmp_path / "gate.js").write_text(script)
    res = subprocess.run([_node(), str(tmp_path / "gate.js"), str(tmp_path / "in.json")],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    for th, row in zip(settings, out["grid"]):
        for r, got in zip(recs, row):
            assert got == decide(to_parsed(r), th).outcome, (r["id"], th, got)
    for r, got in zip(edges, out["edges"]):
        assert got == decide(to_parsed(r), data["defaults"]).outcome, (r, got)
