#!/usr/bin/env python3
"""Build the Threshold Lab (outputs/lab/index.html) from work/results/decisions_*.jsonl.

Move the gate thresholds and see which recorded decisions change. The model answers are
fixed; only the code's decision is re-run. Static HTML, no server, no API calls:

  ./jev/bin/python scripts/build_lab.py

The page's gate is a rule table (RULES below) evaluated by a ten-line JS function. The table
mirrors zeroops/policy.decide in the same order; tests/test_lab_parity.py checks the table and
the JS evaluator against policy.decide on every recorded answer and across the slider ranges.
Numbers in the copy come from work/results/facts.json or are computed here from the decision logs.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops.facts import LABELS, ORDER, parsed_from_pred  # noqa: E402
from zeroops.paths import FACTS, HUB, LAB_DATA as DATA_OUT, LAB_PAGE as OUT, LAB_DIR, decisions, href, rel  # noqa: E402
from zeroops.policy import AUTO_ACTIONS, DEFAULT_THRESHOLDS, GATING_QUESTIONS, decide  # noqa: E402
from zeroops.schema import ACCEPTABLE_ACTIONS  # noqa: E402


# The gate as data, in zeroops/policy.decide order (first match wins; no match = AUTO).
#   0 missing answer -> 1 model proposes escalate -> 2 page -> 3 not an incident
#   -> 4 action gates -> 5 rollback gate.
# Fields refer to the compact records below; "th" names a key of DEFAULT_THRESHOLDS.
RULES = [
    {"id": "missing", "label": "a gating answer is missing (fail closed)",
     "if": {"field": "missing", "op": "true"}, "outcome": "ESCALATE"},
    {"id": "model_escalate", "label": "model proposed escalate",
     "if": {"field": "action", "op": "eq", "value": "escalate"}, "outcome": "ESCALATE"},
    {"id": "page", "label": "needs_page at or above the page cut-off",
     "if": {"field": "page", "op": "ge", "th": "page_min"}, "outcome": "ESCALATE"},
    {"id": "not_incident", "label": "real_incident below the minimum",
     "if": {"field": "real", "op": "lt", "th": "real_incident_min"}, "outcome": "OBSERVE"},
    {"id": "action_not_auto", "label": "action is not on the auto-approved list",
     "if": {"field": "action", "op": "not_in", "value": sorted(AUTO_ACTIONS)}, "outcome": "ESCALATE"},
    {"id": "action_conf", "label": "action confidence below the minimum",
     "if": {"field": "aconf", "op": "lt", "th": "action_conf_min"}, "outcome": "ESCALATE"},
    {"id": "risk", "label": "action_risk above the maximum",
     "if": {"field": "risk", "op": "gt", "th": "risk_max"}, "outcome": "ESCALATE"},
    {"id": "severity", "label": "severity above the maximum",
     "if": {"field": "sev", "op": "gt", "th": "severity_auto_max"}, "outcome": "ESCALATE"},
    {"id": "rollback_deploy", "label": "rollback: deploy_correlated below the minimum",
     "only_action": "rollback",
     "if": {"field": "depc", "op": "lt", "th": "rollback_deploy_corr_min"}, "outcome": "ESCALATE"},
    {"id": "rollback_safe", "label": "rollback: safe_to_autorollback below the minimum",
     "only_action": "rollback",
     "if": {"field": "safe", "op": "lt", "th": "rollback_safe_min"}, "outcome": "ESCALATE"},
]

# Sliders in the order the gate checks them: (threshold key, label, min, max, step)
SLIDERS = [
    ("page_min", "Page a person if needs_page ≥", 0, 1, 0.05),
    ("real_incident_min", "Log only if real_incident <", 0, 1, 0.05),
    ("action_conf_min", "Act only if action confidence ≥", 0, 1, 0.05),
    ("risk_max", "Act only if action_risk ≤ (scale 0–2)", 0, 2, 0.1),
    ("severity_auto_max", "Act only if severity ≤ (scale 0–3)", 0, 3, 0.1),
    ("rollback_deploy_corr_min", "Rollback only if deploy_correlated ≥", 0, 1, 0.05),
    ("rollback_safe_min", "Rollback only if safe_to_autorollback ≥", 0, 1, 0.05),
]


def compact(r: dict) -> dict:
    """The fields the page needs, unrounded so the JS gate sees what policy.decide saw."""
    p, gt, cor = r["pred"], r["ground_truth"], r["correct"]
    return {
        "id": r["incident_id"], "arch": r["archetype"],
        "real": p["real_incident"], "page": p["needs_page"],
        "action": p["proposed_action"], "aconf": p["action_confidence"],
        "risk": p["action_risk"], "depc": p["deploy_correlated"],
        "safe": p["safe_to_autorollback"], "sev": p["severity"],
        "missing": any(q in (p.get("missing") or []) for q in GATING_QUESTIONS),
        "gt_real": gt["real_incident"], "gt_safe": gt["auto_safe"], "gt_action": gt["correct_action"],
        "exact": bool(cor["action"]),
        "acceptable": p["proposed_action"] in ACCEPTABLE_ACTIONS.get(r["archetype"], set()),
        "cat_conf": p["category_confidence"], "cat_ok": bool(cor["failure_category"]),
        "lat": r["latency_ms"],
        # expected outcome at the default thresholds, from zeroops.policy.decide
        "exp": decide(parsed_from_pred(p)).outcome,
    }


def load_records() -> dict[str, list[dict]]:
    out = {}
    for name in ORDER:
        f = decisions(name)
        if not f.exists():
            continue
        recs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        out[name] = [r for r in recs if not r.get("error") and "pred" in r]
    return out


def try_rollback_safety(recs: list[dict]) -> dict | None:
    """Find the rollback-safety setting (on the slider grid) that lets data-corruption
    rollbacks through, and count them with policy.decide. None if there is no such case."""
    dc = [r for r in recs if r["archetype"] == "data_corruption"]
    held = [r for r in dc if r["pred"]["proposed_action"] == "rollback"
            and decide(parsed_from_pred(r["pred"])).outcome != "AUTO"]
    if not held:
        return None
    step = 0.05
    x = math.floor(min(r["pred"]["safe_to_autorollback"] for r in held) / step + 1e-9) * step
    x = round(x, 2)
    th = {"rollback_safe_min": x}
    k = sum(decide(parsed_from_pred(r["pred"]), th).outcome == "AUTO" for r in dc)
    return {"rollback_safe_min": x, "auto": k, "of": len(dc)} if k else None


def build() -> tuple[dict, str]:
    facts = json.loads(FACTS.read_text())
    per = load_records()
    order = [k for k in ORDER if k in per]
    meta = {}
    for k in order:
        b = facts["backends"][k]
        meta[k] = {"label": b["label"], "cost_per_1k_usd": b["cost_per_1k_usd"],
                   "cost_basis": b["cost_basis"], "local": b["cost_per_1k_usd"] == 0
                   and b["cost_basis"].startswith("no API fee"),
                   "ece": b["calibration_ece"], "p50_ms": b["p50_ms"], "p95_ms": b["p95_ms"]}
    n, n_t = facts["n"], facts["n_templates"]
    tr = try_rollback_safety(per.get("jev_native", []))
    data = {
        "labels": {k: LABELS.get(k, k) for k in order},
        "order": order,
        "corpus_version": facts["corpus_version"],
        "defaults": dict(DEFAULT_THRESHOLDS),
        "rules": RULES,
        "sliders": [{"key": k, "label": lab, "min": lo, "max": hi, "step": st}
                    for k, lab, lo, hi, st in SLIDERS],
        "meta": meta,
        "try": tr,
        "backends": {k: [compact(r) for r in per[k]] for k in order},
    }
    if tr:
        try_html = (f"<b>Try this.</b> Set rollback safety to {tr['rollback_safe_min']:.2f} with "
                    f"{LABELS['jev_native']} selected. {tr['auto']} of the {tr['of']} data-corruption "
                    f"incidents, which we labelled as never to be automated, are then rolled back with "
                    f"nobody paged. For those, the rollback checks were the only thing that stopped them.")
    else:
        try_html = ""
    fills = {
        "N": str(n), "N_TEMPLATES": str(n_t), "N_VARIANTS": str(n // n_t if n_t else n),
        "CORPUS": facts["corpus_version"], "TRY": try_html, "HUB_HREF": href(HUB, LAB_DIR),
    }
    html = TEMPLATE
    for key, val in fills.items():
        html = html.replace("{{" + key + "}}", val)
    html = html.replace("/*__LAB_DATA__*/", json.dumps(data, separators=(",", ":")))
    return data, html


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Threshold Lab</title>
<style>
  :root{--navy:#0a2540;--teal:#00838a;--gray:#5b6472;--lg:#f4f6f8;--line:#e2e6ea;
        --red:#c83737;--green:#1b8a60;--amber:#b86a00;--ink:#111827;--bg:#fff;--amberbg:#fff4e0;
        --redbg:#fdecec;--greenbg:#eaf7f1}
  *{box-sizing:border-box}
  body{margin:0;font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);background:var(--bg)}
  header{padding:16px 24px;border-bottom:3px solid var(--navy);display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px}
  .back{display:inline-block;font-size:12.5px;color:var(--teal);text-decoration:none;margin-bottom:6px}
  .back:hover,.back:focus-visible{text-decoration:underline}
  h1{margin:0;font-size:22px;color:var(--navy)}
  .sub{color:var(--gray);font-size:13.5px;margin-top:4px;max-width:760px;line-height:1.45}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{font-size:13px;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;cursor:pointer;color:#334155}
  .chip.active{background:var(--navy);color:#fff;border-color:var(--navy)}
  main{display:grid;grid-template-columns:340px 1fr;min-height:calc(100vh - 90px)}
  .side{padding:16px 20px;border-right:1px solid var(--line);background:var(--lg)}
  .side h2,.pan h2{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--gray);margin:0 0 10px;font-weight:700}
  .slider{margin-bottom:12px}
  .slider label{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;color:#334155;margin-bottom:3px}
  .slider .v{font-variant-numeric:tabular-nums;font-weight:700;color:var(--navy)}
  .slider.changed label{color:var(--amber)}
  input[type=range]{width:100%;accent-color:var(--teal)}
  .reset{width:100%;padding:8px;border:1px solid var(--navy);background:#fff;color:var(--navy);border-radius:8px;cursor:pointer;font-weight:600}
  .box{font-size:12.5px;color:#334155;line-height:1.5;background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-top:12px}
  .box.try{border-left:4px solid var(--amber)}
  .pan{padding:16px 22px;min-width:0}
  .kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
  .kpi{border:1px solid var(--line);border-top:4px solid var(--teal);border-radius:10px;padding:9px 12px}
  .kpi .n{font-size:24px;font-weight:800;color:var(--navy);font-variant-numeric:tabular-nums}
  .kpi .l{font-size:12px;color:#334155;margin-top:2px}
  .kpi .s{font-size:11.5px;color:var(--gray);margin-top:3px;line-height:1.35}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px;min-width:0}
  canvas{width:100%;height:230px;display:block}
  .bar{display:flex;height:28px;border-radius:6px;overflow:hidden;border:1px solid var(--line)}
  .bar span{display:flex;align-items:center;justify-content:center;font-size:12px;color:#fff;white-space:nowrap;overflow:hidden}
  .legend{display:flex;gap:16px;font-size:12px;color:var(--gray);margin-top:8px;flex-wrap:wrap}
  .dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
  th{color:var(--gray);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;position:sticky;top:0;background:#fff}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  tr.danger{background:var(--redbg)} tr.missed{background:var(--amberbg)} tr.safe-esc{background:var(--greenbg)}
  .pill{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;color:#fff}
  .pill.AUTO{background:var(--green)}.pill.ESCALATE{background:var(--red)}.pill.OBSERVE{background:var(--gray)}
  .m-exact{color:var(--green);font-weight:600}.m-acc{color:var(--amber);font-weight:600}.m-no{color:var(--red);font-weight:600}
  .note{font-size:12px;color:var(--gray);line-height:1.5;margin-top:6px}
  .scroll{max-height:340px;overflow:auto;border:1px solid var(--line);border-radius:10px}
  footer{font-size:11.5px;color:var(--gray);padding:10px 22px 18px}
  code{font-size:11.5px}
  @media (max-width:980px){
    main{grid-template-columns:1fr}
    .side{border-right:0;border-bottom:1px solid var(--line)}
    .row{grid-template-columns:1fr}
    .kpis{grid-template-columns:repeat(2,1fr)}
    header{padding:14px 16px}.pan{padding:14px 16px}
  }
</style>
</head>
<body>
<header>
  <div>
    <a class="back" href="{{HUB_HREF}}">&larr; All deliverables</a>
    <h1>Threshold Lab</h1>
    <div class="sub">Move the gate's thresholds and see which of the {{N}} recorded decisions change.
      The model's answers were recorded once and stay fixed; only the decision made by the code changes.</div>
  </div>
  <div class="chips" id="chips"></div>
</header>
<main>
  <aside class="side">
    <h2>Gate thresholds, in the order they are checked</h2>
    <div id="sliders"></div>
    <button class="reset" id="reset">Reset to the defaults in policy.py</button>
    <div class="box">Before these checks the gate applies two fixed rules: a missing answer pages a
      person, and so does a model that proposes "escalate". Order and defaults are those in
      <code>zeroops/policy.py</code>; <code>tests/test_lab_parity.py</code> checks this page against it.
      The defaults were set by hand before the first run and have not been tried on any incident
      outside these {{N}}.</div>
    <div class="box try" id="try">{{TRY}}</div>
    <div class="box"><b>What this page can't show.</b> These are {{N}} synthetic incidents
      ({{N_TEMPLATES}} templates × {{N_VARIANTS}} variants), labelled by the people who wrote the gate.
      The page shows how much the outcome depends on numbers someone has to choose. It can't show
      which numbers would be right for real incidents. Two questions it raises for IT: what does a
      missed major incident cost against an unneeded rollback (Q6), and who owns these numbers after
      go-live and re-checks them at each model release (Q23)?</div>
  </aside>
  <section class="pan">
    <div class="kpis" id="kpis"></div>
    <div class="card">
      <h2>Outcome of the gate, all {{N}} incidents</h2>
      <div class="bar" id="outcomeBar"></div>
      <div class="legend">
        <span><i class="dot" style="background:var(--green)"></i>Act alone (AUTO), nobody paged</span>
        <span><i class="dot" style="background:var(--red)"></i>Page a person (ESCALATE)</span>
        <span><i class="dot" style="background:var(--gray)"></i>Log only (OBSERVE)</span>
      </div>
    </div>
    <div class="row">
      <div class="card">
        <h2>How automation changes with the page cut-off</h2>
        <canvas id="sweep" aria-label="Line chart of automatic actions against the page cut-off"></canvas>
        <div class="note" id="sweepNote"></div>
      </div>
      <div class="card">
        <h2>Category confidence against accuracy</h2>
        <canvas id="reliability" aria-label="Category confidence against accuracy in 0.1-wide groups"></canvas>
        <div class="note" id="calNote"></div>
      </div>
    </div>
    <div class="card">
      <h2>Incidents</h2>
      <div class="note" style="margin:0 0 8px">Red: acted alone on a case we labelled unsafe.
        Amber: a real incident that was only logged. Green: a person was paged on a case we labelled unsafe.
        "Match" compares the model's action with our label: <span class="m-exact">exact</span>, or
        <span class="m-acc">acceptable</span> (on a lenient list we wrote after the first run).</div>
      <div class="scroll"><table id="tbl"></table></div>
    </div>
  </section>
</main>
<footer>Our measurement. Data: <code>work/results/decisions_*.jsonl</code> (corpus {{CORPUS}}), costs and
  latency from <code>work/results/facts.json</code>. Built by <code>scripts/build_lab.py</code>; no API calls.</footer>
<script>
const DATA = /*__LAB_DATA__*/;
const RULES = DATA.rules;
const RULE_LABEL = Object.fromEntries(RULES.map(r=>[r.id, r.label]));
RULE_LABEL.auto = "all checks passed";

/*__GATE_JS_START__*/
function gate(r, th, rules){
  for (const rule of rules){
    if (rule.only_action && r.action !== rule.only_action) continue;
    const c = rule.if, v = r[c.field], ref = ("th" in c) ? th[c.th] : c.value;
    let hit;
    switch (c.op){
      case "true": hit = !!v; break;
      case "eq": hit = v === ref; break;
      case "not_in": hit = !ref.includes(v); break;
      case "ge": hit = v >= ref; break;
      case "lt": hit = v < ref; break;
      case "gt": hit = v > ref; break;
      default: throw new Error("unknown op " + c.op);
    }
    if (hit) return {outcome: rule.outcome, rule: rule.id};
  }
  return {outcome: "AUTO", rule: "auto"};
}
/*__GATE_JS_END__*/

const fromHash = location.hash.slice(1);
let state = {b: DATA.order.includes(fromHash) ? fromHash : DATA.order[0], th: {...DATA.defaults}};

function median(xs){ const s=[...xs].sort((a,b)=>a-b), n=s.length;
  if(!n) return null; return n%2 ? s[(n-1)/2] : (s[n/2-1]+s[n/2])/2; }
function nearestRank(xs,q){ const s=[...xs].sort((a,b)=>a-b); return s.length? s[Math.max(0,Math.ceil(q*s.length)-1)] : null; }

function tally(recs, th){
  const t={n:recs.length, auto:0, esc:0, obs:0, autoExact:0, autoAcc:0, autoOther:0, autoUnsafe:0,
           unsafe:0, unsafePaged:0, real:0, missed:0, autoPage:[]};
  for (const r of recs){
    const o = gate(r, th, RULES).outcome;
    if (o==="AUTO"){ t.auto++; t.autoPage.push(r.page);
      if (r.exact) t.autoExact++; else if (r.acceptable) t.autoAcc++; else t.autoOther++;
      if (!r.gt_safe) t.autoUnsafe++; }
    else if (o==="ESCALATE") t.esc++; else t.obs++;
    if (!r.gt_safe){ t.unsafe++; if (o==="ESCALATE") t.unsafePaged++; }
    if (r.gt_real){ t.real++; if (o==="OBSERVE") t.missed++; }
  }
  return t;
}

function fmtTh(key, v){ return (key==="risk_max"||key==="severity_auto_max") ? Number(v).toFixed(1) : Number(v).toFixed(2); }

function costTile(m){
  if (m.local) return ["no API fee", "API cost per 1,000 calls", "local GPU; GPU and power not costed"];
  const est = m.cost_basis.startsWith("estimated");
  return ["$"+Number(m.cost_per_1k_usd).toPrecision(2)+(est?" (est.)":""), "API cost per 1,000 calls", m.cost_basis];
}

function setupCanvas(id){
  const cv=document.getElementById(id), dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth, h=cv.clientHeight; cv.width=w*dpr; cv.height=h*dpr;
  const x=cv.getContext("2d"); x.scale(dpr,dpr); x.clearRect(0,0,w,h); return [x,w,h];
}

function drawSweep(){
  const [x,w,h]=setupCanvas("sweep");
  const recs=DATA.backends[state.b];
  const xs=[]; for(let i=10;i<=20;i++) xs.push(i/20);   // 0.50 .. 1.00
  const pts=xs.map(v=>({v, t:tally(recs,{...state.th, page_min:v})}));
  const ymax=Math.max(5, Math.ceil(Math.max(...pts.map(p=>p.t.auto))/5)*5);
  const L=40,R=12,T=14,B=34, W=w-L-R, H=h-T-B;
  const px=v=>L+W*(v-0.5)/0.5, py=c=>T+H*(1-c/ymax);
  x.font="11px system-ui, Arial"; x.lineWidth=1;
  for (let c=0;c<=ymax;c+=ymax/5){ x.strokeStyle="#eef1f4"; x.beginPath(); x.moveTo(L,py(c)); x.lineTo(L+W,py(c)); x.stroke();
    x.fillStyle="#5b6472"; x.fillText(String(Math.round(c)), 18, py(c)+4); }
  [0.5,0.6,0.7,0.8,0.9,1.0].forEach(v=>{ x.fillStyle="#5b6472"; x.fillText(v.toFixed(1), px(v)-8, T+H+15); });
  x.fillText("page cut-off (needs_page ≥ this pages a person)", L+W-262, T+H+29);
  x.save(); x.translate(10, T+H/2+30); x.rotate(-Math.PI/2); x.fillText("incidents", 0, 0); x.restore();
  const line=(f,color)=>{ x.strokeStyle=color; x.lineWidth=2.4; x.beginPath();
    pts.forEach((p,i)=>{ const X=px(p.v), Y=py(f(p.t)); i? x.lineTo(X,Y) : x.moveTo(X,Y); }); x.stroke(); };
  line(t=>t.auto,"#0a2540"); line(t=>t.autoAcc+t.autoOther,"#b86a00"); line(t=>t.autoUnsafe,"#c83737");
  const cur=tally(recs,state.th);
  x.strokeStyle="#00838a"; x.setLineDash([4,4]); x.beginPath(); x.moveTo(px(Math.min(1,Math.max(0.5,state.th.page_min))),T);
  x.lineTo(px(Math.min(1,Math.max(0.5,state.th.page_min))),T+H); x.stroke(); x.setLineDash([]);
  x.font="bold 11px system-ui, Arial";
  x.fillStyle="#0a2540"; x.fillText("acted alone", L+6, T+12);
  x.fillStyle="#b86a00"; x.fillText("…with an action other than our label", L+84, T+12);
  x.fillStyle="#c83737"; x.fillText("…on a case labelled unsafe", L+6, T+26);
  const maxUnsafe=Math.max(...pts.map(p=>p.t.autoUnsafe));
  let note=`Each point re-runs the gate at that page cut-off with your other settings (dashed line: current cut-off).`;
  note += maxUnsafe===0 ? ` At these settings no case labelled unsafe is automated anywhere on the curve, so the red line stays at zero.`
                        : ` At these settings up to ${maxUnsafe} case(s) labelled unsafe are automated somewhere on the curve.`;
  if (cur.auto){ const lo=Math.min(...cur.autoPage), hi=Math.max(...cur.autoPage);
    note += ` On the ${cur.auto} cases it acts on now, needs_page runs from ${lo.toFixed(2)} to ${hi.toFixed(2)}.`; }
  document.getElementById("sweepNote").textContent = note;
}

function drawReliability(){
  const [x,w,h]=setupCanvas("reliability");
  const recs=DATA.backends[state.b];
  const bins=Array.from({length:10},()=>({n:0,ok:0,conf:0}));
  for (const r of recs){ const b=Math.min(9, Math.floor(r.cat_conf*10)); bins[b].n++; bins[b].ok+=r.cat_ok?1:0; bins[b].conf+=r.cat_conf; }
  const L=34,R=12,T=24,B=34, W=w-L-R, H=h-T-B;
  const px=v=>L+W*v, py=v=>T+H*(1-v);
  x.font="11px system-ui, Arial";
  for (let v=0; v<=1.0001; v+=0.25){ x.strokeStyle="#eef1f4"; x.beginPath(); x.moveTo(L,py(v)); x.lineTo(L+W,py(v)); x.stroke();
    x.fillStyle="#5b6472"; x.fillText(Math.round(v*100)+"%", 2, py(v)+4); }
  for (let v=0; v<=1.0001; v+=0.1){ x.fillStyle="#5b6472"; x.fillText(v.toFixed(1), px(v)-8, T+H+15); }
  x.fillText("stated confidence (groups 0.1 wide)", L+W-200, T+H+29);
  x.setLineDash([4,4]); x.strokeStyle="#aab4c0"; x.beginPath(); x.moveTo(px(0),py(0)); x.lineTo(px(1),py(1)); x.stroke(); x.setLineDash([]);
  let used=0;
  bins.forEach(b=>{ if(!b.n) return; used++; const c=b.conf/b.n, a=b.ok/b.n;
    x.fillStyle="rgba(0,131,138,.18)"; x.fillRect(px(c)-8, py(a), 16, py(0)-py(a));
    x.fillStyle="#0a2540"; x.beginPath(); x.arc(px(c),py(a),4,0,7); x.fill();
    x.fillStyle="#334155"; x.fillText(`n=${b.n}`, px(c)-12, py(a)-9); });
  const m=DATA.meta[state.b];
  document.getElementById("calNote").textContent =
    `Each dot is a group of failure_category answers with similar stated confidence, plotted at its accuracy; `+
    `the dashed line is where the two would be equal. Groups this small move a long way with one answer, so `+
    `read it as the method, not as proof that the probabilities can be trusted. Expected calibration error `+
    `${m.ece} over ${recs.length} answers. This chart does not depend on the thresholds.`;
}

function pill(o){ return `<span class="pill ${o}">${o}</span>`; }

function render(){
  document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("active", c.dataset.b===state.b));
  const recs=DATA.backends[state.b], m=DATA.meta[state.b], t=tally(recs,state.th);
  const lat=recs.map(r=>r.lat), p50=median(lat), p95=nearestRank(lat,0.95);
  const [cn,cl,cs]=costTile(m);
  const tiles=[
    [`${t.auto}`, `act alone (AUTO), of ${t.n}`, `${t.esc} page a person, ${t.obs} log only`],
    t.auto ? [`${t.autoExact} of ${t.auto}`, `automatic actions that exactly match our label`,
      `${t.autoAcc} more are on the acceptable list (written after the first run); ${t.autoOther} are on neither`]
           : [`none`, `automatic actions to compare with our label`, `nothing is automated at these settings`],
    [`${t.autoUnsafe}`, `automatic actions on a case labelled unsafe`,
      `unsafe cases paged: ${t.unsafePaged} of ${t.unsafe}`],
    [`${t.missed}`, `real incidents only logged (missed), of ${t.real}`, `a missed incident pages nobody`],
    [`${Math.round(p50)} ms`, `median latency per call`, `p95 ${Math.round(p95)} ms; does not change with thresholds`],
    [cn, cl, cs],
  ];
  document.getElementById("kpis").innerHTML = tiles.map(([n,l,s],i)=>{
    const col = i===2 ? (t.autoUnsafe? "var(--red)":"var(--green)") : i===3 ? (t.missed? "var(--amber)":"var(--green)") : i===1 ? "var(--amber)" : "var(--teal)";
    return `<div class="kpi" style="border-top-color:${col}"><div class="n">${n}</div><div class="l">${l}</div><div class="s">${s}</div></div>`; }).join("");
  const tot=t.n||1;
  document.getElementById("outcomeBar").innerHTML =
    `<span style="width:${100*t.auto/tot}%;background:var(--green)">${t.auto} act alone</span>`+
    `<span style="width:${100*t.esc/tot}%;background:var(--red)">${t.esc} page a person</span>`+
    `<span style="width:${100*t.obs/tot}%;background:var(--gray)">${t.obs} log only${t.missed? ` (${t.missed} real)`:""}</span>`;
  drawSweep(); drawReliability();
  const rows=recs.map(r=>{ const g=gate(r,state.th,RULES), o=g.outcome;
    const cls=(o==="AUTO"&&!r.gt_safe)?"danger":(o==="OBSERVE"&&r.gt_real)?"missed":(o==="ESCALATE"&&!r.gt_safe)?"safe-esc":"";
    const match=r.exact?'<span class="m-exact">exact</span>':r.acceptable?'<span class="m-acc">acceptable</span>':'<span class="m-no">no</span>';
    return `<tr class="${cls}"><td>${r.id}</td><td>${r.arch}</td><td>${r.action}</td><td>${r.gt_action}</td><td>${match}</td>
      <td class="num">${r.page.toFixed(2)}</td><td class="num">${r.aconf.toFixed(2)}</td><td>${pill(o)}</td><td>${RULE_LABEL[g.rule]}</td></tr>`; }).join("");
  document.getElementById("tbl").innerHTML =
    `<thead><tr><th>Incident</th><th>Template</th><th>Model's action</th><th>Our label</th><th>Match</th>
     <th>needs_page</th><th>Action conf.</th><th>Gate outcome</th><th>First check that decided it</th></tr></thead><tbody>${rows}</tbody>`;
  for (const s of DATA.sliders){
    document.getElementById("v-"+s.key).textContent = fmtTh(s.key, state.th[s.key]);
    document.getElementById("w-"+s.key).classList.toggle("changed", Math.abs(state.th[s.key]-DATA.defaults[s.key])>1e-9);
  }
}

function init(){
  document.getElementById("chips").innerHTML = DATA.order.map(k=>
    `<button class="chip" data-b="${k}">${DATA.labels[k]}</button>`).join("");
  document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{state.b=c.dataset.b;
    try { history.replaceState(null, "", "#"+state.b); } catch(e) {} render();});
  document.getElementById("sliders").innerHTML = DATA.sliders.map(s=>
    `<div class="slider" id="w-${s.key}"><label for="s-${s.key}">${s.label}<span class="v" id="v-${s.key}"></span></label>
     <input type="range" id="s-${s.key}" min="${s.min}" max="${s.max}" step="${s.step}"></div>`).join("");
  for (const s of DATA.sliders){
    const el=document.getElementById("s-"+s.key); el.value=state.th[s.key];
    el.oninput=()=>{ state.th[s.key]=parseFloat(el.value); render(); };
  }
  document.getElementById("reset").onclick=()=>{ state.th={...DATA.defaults};
    for (const s of DATA.sliders) document.getElementById("s-"+s.key).value=state.th[s.key]; render(); };
  if (!DATA.try) document.getElementById("try").style.display="none";
  window.addEventListener("resize", ()=>{drawSweep(); drawReliability();});
  render();
}
init();
</script>
</body>
</html>
"""


def main() -> int:
    data, html = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    DATA_OUT.write_text(json.dumps(data, indent=2))
    print(f"wrote {rel(OUT)} ({len(html)/1024:.0f} KB) and {rel(DATA_OUT)}; backends={data['order']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
