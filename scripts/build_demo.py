#!/usr/bin/env python3
"""Generate the 30-second dashboard loop (video/dashboard-loop/index.html), a HyperFrames composition.

The loop is silent: on-screen captions only, no voiceover. Every number in the captions and
the metrics strip comes from work/results/facts.json; the incidents come from work/results/demo_data.json,
and the gate rows are computed with zeroops.policy.explain/decide on the logged answers, so
nothing about the policy is re-implemented in the page.

  ./jev/bin/python scripts/build_demo.py
  export PATH=/media/alfonso/shared/jev_local/node22/bin:$PATH
  cd video/dashboard-loop && npx --yes hyperframes@0.8.114 check \
      && npx --yes hyperframes@0.8.114 render -o ../../../outputs/6_dashboard-loop.mp4

Opened in a browser, the composition also works as a small dashboard: the backend chips switch
which backend's answers are shown. The same page is written to outputs/dashboard/index.html
so the hub can link it while only outputs/ is served. Paths are in zeroops/paths.py.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops.facts import parsed_from_pred  # noqa: E402
from zeroops.paths import DASHBOARD_PAGE, DEMO_DATA, FACTS, LOOP_PAGE, decisions, rel  # noqa: E402
from zeroops.policy import AUTO_ACTIONS, decide, explain  # noqa: E402
from zeroops.schema import ACCEPTABLE_ACTIONS, incident_questions  # noqa: E402

DURATION = 30.5
CLOSE = 0.05          # a passing check within this margin is flagged "close"

OPS = {"<": "&lt;", "<=": "&le;", ">=": "&ge;"}


def fmt_th(v: float) -> str:
    return f"{v:.2f}" if v < 1 else f"{v:.1f}"


def gate_rows(pred: dict) -> list[dict]:
    """Display rows for the gate panel, in policy order, from zeroops.policy.explain."""
    p = parsed_from_pred(pred)
    checks = explain(p)
    rows = []
    if p.missing:
        rows.append({"label": "all gating answers present", "value": ", ".join(p.missing),
                     "passed": False, "margin": None, "close": False})
    for c in checks:
        rows.append({"label": f"{c['check']} {OPS[c['op']]} {fmt_th(c['threshold'])}",
                     "value": f"{c['value']:.2f}", "passed": c["passed"],
                     "margin": c["margin"], "close": c["passed"] and abs(c["margin"]) <= CLOSE})
        if c["check"] == "real_incident":   # the action check sits here in policy order
            rows.append({"label": "action is on the auto-approved list", "value": p.proposed_action or "—",
                         "passed": p.proposed_action in AUTO_ACTIONS, "margin": None, "close": False})
    return rows


def load_examples(demo: dict) -> list[dict]:
    """demo_data examples, with gate rows and the policy's outcome attached."""
    out = []
    for group in demo["examples"]:
        b = group["backend"]
        logged = {}
        for line in decisions(b).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                logged[r["incident_id"]] = r
        exs = []
        for e in group["examples"]:
            rec = logged[e["id"]]
            d = decide(parsed_from_pred(rec["pred"]))
            assert d.outcome == e["outcome"], (b, e["id"], d.outcome, e["outcome"])
            exs.append({**e, "gate": gate_rows(rec["pred"]), "outcome": d.outcome,
                        "decided_action": d.action, "rationale": d.rationale})
        out.append({"backend": b, "label": group["label"], "examples": exs})
    return out


def money_1k(b: dict) -> str:
    if b["cost_per_1k_usd"] == 0 and b["cost_basis"].startswith("no API fee"):
        return "no API fee (local)"
    est = " (est.)" if b["cost_basis"].startswith("estimated") else ""
    return f"${b['cost_per_1k_usd']:.2g} per 1k{est}"


def metric_cards(facts: dict, order: list[str]) -> list[dict]:
    cards = []
    for k in order:
        b = facts["backends"][k]
        n = b["n_answered"]
        if b["auto"]:
            acted = f"acted alone {b['auto']} · {b['auto_exact']} exact"
        else:
            acted = "never acted alone"
        cards.append({
            "name": b["label"],
            "l1": f"category {b['category']['k']}/{n} · exact action {b['action_exact']['k']}/{n}",
            "bar": b["action_exact"]["pct"],
            "l2": f"{acted} · unsafe automated {b['unsafe_auto']}/{b['unsafe_cases']}",
            "l3": f"missed real incidents {b['missed_incidents']} · median {b['p50_ms']:.0f} ms",
            "l4": money_1k(b),
        })
    return cards


def captions(facts: dict) -> list[dict]:
    ex = facts["jev"]["examples"]["auto"]
    j = facts["backends"]["jev_native"]
    n_q = len(incident_questions())
    close = [c for c in ex["checks"] if c["passed"] and abs(c["margin"]) <= CLOSE]
    names = {"needs_page": "needs_page", "safe_to_autorollback": "rollback safety"}
    close_txt = ", ".join(f"{names.get(c['check'], c['check'])} {c['value']:.2f} against "
                          f"{'a ' if c['check'] == 'needs_page' else ''}{c['threshold']:.2f}"
                          f"{' cut-off' if c['check'] == 'needs_page' else ''}" for c in close)
    all_pass = all(c["passed"] for c in ex["checks"])
    if ex["outcome"] == "AUTO" and all_pass:
        verdict = f"Every check passes, so the gate runs a {ex['action']} with nobody paged."
    else:
        verdict = f"The gate's decision: {ex['outcome']} ({ex['rationale']})."
    if close:
        verdict += (f" {_word(len(close)).capitalize()} {'checks were' if len(close) > 1 else 'check was'} "
                    f"close: {close_txt}.")
    summary = ex["state"].split("summary: ", 1)[1].split("\n", 1)[0] if "summary: " in ex["state"] else ""
    return [
        {"start": 0.3, "end": 5.6,
         "text": f"One synthetic test incident, {ex['id']}: {summary}."},
        {"start": 5.6, "end": 11.6,
         "text": f"Jev gets the alert text and {n_q} typed questions. One call returns all {n_q} "
                 f"answers, each a choice or a score with its probability."},
        {"start": 11.6, "end": 16.2,
         "text": "Ordinary code checks the answers against fixed thresholds, in order. "
                 "The thresholds are in zeroops/policy.py."},
        {"start": 16.2, "end": 22.6, "text": verdict},
        {"start": 22.6, "end": DURATION,
         "text": f"Across {facts['n']} synthetic incidents the gate let Jev act alone {j['auto']} times; "
                 f"{j['auto_exact']} of those matched our labelled fix. None of the {j['unsafe_cases']} "
                 f"cases we labelled unsafe was automated."},
    ]


def _word(n: int) -> str:
    words = "zero one two three four five six seven eight nine ten".split()
    return words[n] if 0 <= n < len(words) else str(n)


def autos_not_exact() -> tuple[int, int]:
    """Jev native's automatic actions that missed our label: (on the acceptable list, on neither)."""
    acc = other = 0
    for line in decisions("jev_native").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("error") or r["decision"]["outcome"] != "AUTO" or r["correct"]["action"]:
            continue
        if r["pred"]["proposed_action"] in ACCEPTABLE_ACTIONS.get(r["archetype"], set()):
            acc += 1
        else:
            other += 1
    return acc, other


def footer(facts: dict) -> str:
    j = facts["backends"]["jev_native"]
    acc, other = autos_not_exact()
    if other:
        rest = (f"of Jev's other automatic actions, {acc} used an alternative from a list written after "
                f"the first run and {other} matched neither")
    else:
        rest = f"Jev's other {acc} automatic actions used an alternative from a list written after the first run"
    return (f"Our measurement · n={facts['n']} synthetic incidents ({facts['n_templates']} templates × "
            f"{facts['n'] // facts['n_templates']}) · {rest} · the {j['unsafe_cases']} unsafe "
            f"cases come from {j['unsafe_templates']} scenario types, too few to estimate a real rate")


def build() -> str:
    facts = json.loads(FACTS.read_text())
    demo = json.loads(DEMO_DATA.read_text())
    examples = load_examples(demo)
    order = [g["backend"] for g in examples]
    data = {"examples": examples, "metrics": metric_cards(facts, order)}
    caps = captions(facts)
    cap_html = "\n        ".join(f'<div class="cap" id="cap{i}">{html.escape(c["text"])}</div>'
                                for i, c in enumerate(caps))
    sub = (f"{len(incident_questions())} typed questions, one API call · thresholds in zeroops/policy.py · "
           f"{facts['n']} synthetic incidents")
    page = TEMPLATE
    for k, v in {"__DEMO_DATA__": json.dumps(data, separators=(",", ":")),
                 "__CAPTIONS__": json.dumps(caps), "__CAP_HTML__": cap_html,
                 "__SUBTITLE__": html.escape(sub), "__FOOTER__": html.escape(footer(facts)),
                 "__DURATION__": f"{DURATION}"}.items():
        page = page.replace(k, v)
    return page


TEMPLATE = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>ZeroOps loop</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin:0; padding:0; box-sizing:border-box; }
      html, body { width:1920px; height:1080px; overflow:hidden; background:#080b14;
        font-family: Inter, ui-sans-serif, system-ui, "Segoe UI", sans-serif; color:#e6edf7; }
      #root { width:100%; height:100%; padding:30px 44px 22px; display:flex; flex-direction:column; gap:16px;
        background: radial-gradient(1200px 600px at 20% -10%, #16223c 0%, #080b14 55%); }
      header { display:flex; align-items:flex-end; justify-content:space-between; }
      #title { font-size:42px; font-weight:700; letter-spacing:-0.01em; }
      #title .accent { color:#5eead4; }
      #subtitle { font-size:19px; color:#b3c2d8; margin-top:6px; }
      .controls { display:flex; gap:8px; align-items:center; }
      .chip { font-size:15px; padding:7px 13px; border-radius:999px; border:1px solid #26344f;
        background:#0f172a; color:#b9c6da; cursor:pointer; font-family:inherit; }
      .chip.active { background:#12385f; border-color:#38bdf8; color:#e0f2fe; }
      #captions { position:relative; height:92px; flex-shrink:0; border-radius:14px;
        background:rgba(94,234,212,.07); border:1px solid #1f3b4a; }
      .cap { position:absolute; inset:0; display:flex; align-items:center; padding:0 26px;
        font-size:29px; line-height:1.35; color:#f1f6fc; font-weight:500; opacity:0; visibility:hidden; }
      main { flex:1; display:grid; grid-template-columns: 1.05fr 1.35fr 1.2fr; gap:16px; min-height:0; }
      .panel { background:rgba(15,23,42,.78); border:1px solid #1e2b45; border-radius:16px;
        padding:14px 18px; display:flex; flex-direction:column; min-height:0; overflow:hidden; }
      .panel h2 { font-size:14px; letter-spacing:.12em; text-transform:uppercase; color:#93a7c4; margin-bottom:10px;
        display:flex; justify-content:space-between; align-items:center; }
      .tag { font-size:13px; color:#7dd3fc; border:1px solid #38bdf8; padding:2px 8px; border-radius:6px; font-weight:700; letter-spacing:.04em; }
      #incident-text { font-family: "DejaVu Sans Mono", ui-monospace, "SF Mono", Menlo, monospace; font-size:15px; line-height:1.5;
        color:#d3deee; white-space:pre-wrap; overflow:hidden; }
      .qrow { display:grid; grid-template-columns: 190px 1fr 60px; gap:10px; align-items:center;
        padding:4px 0; border-bottom:1px solid #16223a; }
      .qname { font-size:15px; color:#c9d5e8; }
      .qval { font-size:16px; font-weight:600; color:#eef3fb; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .qtype { font-size:12px; color:#9fb2cc; margin-left:8px; font-weight:400; }
      .bar { height:6px; background:#16223a; border-radius:4px; overflow:hidden; margin-top:3px; }
      .bar > i { display:block; height:100%; background:linear-gradient(90deg,#38bdf8,#5eead4); }
      .gaterow { display:grid; grid-template-columns: 1fr 64px 70px 92px; gap:8px; align-items:center; padding:6px 0;
        border-bottom:1px solid #16223a; font-size:16px; }
      .g-label { color:#c9d5e8; }
      .g-val { font-family:"DejaVu Sans Mono",ui-monospace,Menlo,monospace; color:#e2eaf6; text-align:right; }
      .g-margin { font-family:"DejaVu Sans Mono",ui-monospace,Menlo,monospace; color:#9fb2cc; text-align:right; font-size:14px; }
      .pass { color:#34d399; font-weight:700; text-align:right; }
      .fail { color:#f87171; font-weight:700; text-align:right; }
      .close { color:#fbbf24; border:1px solid #fbbf24; border-radius:999px; font-size:12px; padding:1px 7px; margin-left:6px; font-weight:700; }
      #outcome { margin-top:auto; text-align:center; padding:12px; border-radius:14px; font-size:28px;
        font-weight:800; letter-spacing:.03em; }
      #outcome.AUTO { background:linear-gradient(180deg,#064e3b,#065f46); color:#a7f3d0; border:1px solid #10b981; }
      #outcome.ESCALATE { background:linear-gradient(180deg,#4c1d24,#601019); color:#fecaca; border:1px solid #ef4444; }
      #outcome.OBSERVE { background:linear-gradient(180deg,#1e293b,#334155); color:#cbd5e1; border:1px solid #64748b; }
      #outcome small { display:block; font-size:15px; font-weight:500; margin-top:5px; opacity:.92; letter-spacing:0; }
      #metrics { flex-shrink:0; background:rgba(15,23,42,.78); border:1px solid #1e2b45; border-radius:16px; padding:12px 16px 8px; }
      #cards { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }
      .mcard { background:#0f172a; border:1px solid #1e2b45; border-radius:12px; padding:9px 12px; }
      .mname { font-size:16px; font-weight:700; color:#eef3fb; margin-bottom:3px; }
      .mcell { font-size:14px; color:#d0dbeb; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .mbar { height:5px; background:#16223a; border-radius:4px; overflow:hidden; margin-top:4px; }
      .mbar > i { display:block; height:100%; background:#38bdf8; }
      #mfoot { font-size:13px; color:#9fb2cc; margin-top:8px; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="__DURATION__" data-fps="30" data-width="1920" data-height="1080">
      <header>
        <div>
          <div id="title">ZeroOps demo <span class="accent">· Jev on one incident</span></div>
          <div id="subtitle">__SUBTITLE__</div>
        </div>
        <div class="controls" id="controls"></div>
      </header>

      <section id="captions">
        __CAP_HTML__
      </section>

      <main>
        <section id="panel-incident" class="panel">
          <h2>Incident text <span class="tag" id="arch">–</span></h2>
          <div id="incident-text"></div>
        </section>
        <section id="panel-decisions" class="panel">
          <h2>Typed answers <span style="color:#5eead4">one call · probability per answer</span></h2>
          <div id="questions"></div>
        </section>
        <section id="panel-gate" class="panel">
          <h2>Gate <span style="color:#93a7c4">plain code · checked in order</span></h2>
          <div id="gates"></div>
          <div id="outcome"></div>
        </section>
      </main>

      <section id="metrics">
        <div id="cards"></div>
        <div id="mfoot">__FOOTER__</div>
      </section>
    </div>

    <script>
      const DEMO = __DEMO_DATA__;
      const CAPTIONS = __CAPTIONS__;
      let state = { b:0, i:0 };
      const $ = (s) => document.querySelector(s);
      const pct = (n) => Math.max(0, Math.min(1, n)) * 100;
      const esc = (s) => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

      function questionRows(e) {
        const q = (name, type, value, meter) => `
          <div class="qrow">
            <div class="qname">${name}</div>
            <div><div class="qval">${value}<span class="qtype">${type}</span></div>
            ${meter!==null ? `<div class="bar"><i style="width:${pct(meter)}%"></i></div>`:""}</div>
            <div class="qval" style="text-align:right;color:#b6c4da">${meter!==null?meter.toFixed(2):""}</div>
          </div>`;
        return [
          q("real_incident","yes-prob.", e.real_incident.toFixed(2), e.real_incident),
          q("failure_category","choice", e.category, e.category_confidence),
          q("suspect_component","choice", e.suspect_component, null),
          q("root_cause","choice", e.root_cause, null),
          q("deploy_correlated","yes-prob.", e.deploy_correlated.toFixed(2), e.deploy_correlated),
          q("severity","score 0–3", e.severity.toFixed(2), e.severity_confidence),
          q("blast_radius","score 0–3", e.blast_radius.toFixed(2), null),
          q("customer_impact","yes-prob.", e.customer_impact.toFixed(2), e.customer_impact),
          q("safe_to_autorollback","yes-prob.", e.safe_to_autorollback.toFixed(2), e.safe_to_autorollback),
          q("proposed_action","choice", e.action, e.action_conf),
          q("action_risk","score 0–2", e.action_risk.toFixed(2), null),
          q("needs_page","yes-prob.", e.needs_page.toFixed(2), e.needs_page),
        ].join("");
      }

      function gateRows(e) {
        return e.gate.map(g => `<div class="gaterow"><span class="g-label">${g.label}${g.close?'<span class="close">close</span>':''}</span>
          <span class="g-val">${esc(g.value)}</span><span class="${g.passed?'pass':'fail'}">${g.passed?'PASS':'FAIL'}</span>
          <span class="g-margin">${g.margin===null?'':(g.margin>=0?'+':'')+g.margin.toFixed(2)}</span></div>`).join("");
      }

      function cards() {
        return DEMO.metrics.map(m => `<div class="mcard"><div class="mname">${esc(m.name)}</div>
          <div class="mcell">${esc(m.l1)}</div><div class="mbar"><i style="width:${m.bar}%"></i></div>
          <div class="mcell">${esc(m.l2)}</div><div class="mcell">${esc(m.l3)}</div><div class="mcell">${esc(m.l4)}</div></div>`).join("");
      }

      function render() {
        const group = DEMO.examples[state.b];
        const e = group.examples[state.i % group.examples.length];
        $("#arch").textContent = e.archetype;
        $("#incident-text").textContent = e.state.trim();
        $("#questions").innerHTML = questionRows(e);
        $("#gates").innerHTML = gateRows(e);
        const o = $("#outcome");
        o.className = e.outcome;
        const label = e.gt_action + (e.correct_action ? " (exact match)" : " (different)");
        o.innerHTML = `${e.outcome}${e.outcome==="AUTO" ? " · " + esc(e.decided_action) : ""}<small>${
          e.outcome==="AUTO" ? `nobody paged · our label: ${esc(label)}`
          : e.outcome==="ESCALATE" ? `page a person · ${esc(e.rationale)}`
          : `log only · ${esc(e.rationale)}`}</small>`;
        $("#cards").innerHTML = cards();
        $("#controls").innerHTML = DEMO.examples.map((g,idx)=>
          `<button class="chip ${idx===state.b?'active':''}" data-b="${idx}">${esc(g.label)}</button>`).join("");
        document.querySelectorAll(".chip[data-b]").forEach(b=>b.onclick=()=>{state.b=+b.dataset.b;render();});
      }

      render();
      const tl = gsap.timeline({ paused:true });
      CAPTIONS.forEach((c, i) => {
        tl.fromTo("#cap"+i, { autoAlpha:0, y:8 }, { autoAlpha:1, y:0, duration:0.4 }, c.start);
        if (i < CAPTIONS.length - 1) tl.to("#cap"+i, { autoAlpha:0, duration:0.3 }, c.end - 0.3);
      });
      tl.from("#title",{opacity:0,y:-24,duration:0.7},0.1)
        .from("#subtitle",{opacity:0,y:-10,duration:0.6},0.5)
        .from(".chip",{opacity:0,y:8,stagger:0.06,duration:0.4},0.9)
        .from("#panel-incident",{opacity:0,x:-40,duration:0.7},1.0)
        .from("#panel-decisions",{opacity:0,y:30,duration:0.7},5.8)
        .from(".qrow",{opacity:0,x:-16,stagger:0.25,duration:0.4},6.3)
        .from("#panel-gate",{opacity:0,x:40,duration:0.7},11.7)
        .from(".gaterow",{opacity:0,x:16,stagger:0.3,duration:0.4},12.2)
        .from("#outcome",{opacity:0,scale:0.7,duration:0.6,ease:"back.out(2)"},16.3)
        .from("#metrics",{opacity:0,y:24,duration:0.7},22.7);
      tl.set({}, {}, __DURATION__);
      window.__timelines = window.__timelines || {};
      window.__timelines["main"] = tl;
      tl.seek(0);
      if (location.search.indexOf("end") >= 0) tl.seek(tl.duration());
    </script>
  </body>
</html>
"""


def main() -> int:
    page = build()
    for out in (LOOP_PAGE, DASHBOARD_PAGE):  # render source, and the copy the hub links to
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
    print(f"wrote {rel(LOOP_PAGE)} and {rel(DASHBOARD_PAGE)}  ({len(page)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
