#!/usr/bin/env python3
"""Build the single narrated demo video (work/video/showcase -> outputs/4_demo.mp4).

Visuals are HyperFrames-native: a GSAP timeline, an animated mesh-gradient background, kinetic
titles, HTML/SVG-style diagrams (flow, network example, integration), rolling number counters and
animated bars. The intro and outro reuse the deck's framing. Narration is ElevenLabs TTS, one
segment per scene, so the visuals land with the voice.

  ./jev/bin/python scripts/build_video.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zeroops import paths  # noqa: E402

load_dotenv(paths.ENV)
EL_KEY = os.getenv("ELEVENLABS_API") or os.getenv("ELEVENLABS_API_KEY") or ""
VOICE = os.getenv("VOICE_ID", "bfGb7JTLUnZebZRiFYyq")
SPEED = float(os.getenv("SPEED", "1.05"))
LEAD, TAIL = 0.8, 1.8

FACTS = json.loads(paths.FACTS.read_text())
NAT = FACTS["backends"]["jev_native"]
N, TEMPL = FACTS["n"], FACTS["n_templates"]
P50, COST = round(NAT["p50_ms"]), NAT["cost_per_1k_usd"]
EXACT, EXACT_PCT = NAT["action_exact"]["k"], round(NAT["action_exact"]["pct"])
AUTO, UNSAFE = NAT["auto"], NAT["unsafe_cases"]


def network_example() -> dict:
    recs = [json.loads(l) for l in paths.decisions("jev_native").read_text().splitlines() if l.strip()]
    r = next((x for x in recs if x["archetype"] == "dns_failure"), recs[0])
    p = r["pred"]
    return {"id": r["incident_id"], "outcome": r["decision"]["outcome"],
            "real": p["real_incident"], "category": p["failure_category"],
            "root": p["root_cause"], "severity": p["severity"], "action": p["proposed_action"],
            "page": p["needs_page"], "risk": p["action_risk"]}


EX = network_example()

SCENE_IMG = {'s1': 'hero', 's2': 'industry', 's3': 'gap', 's4': 'jev', 's5': 'example',
             's6': 'example', 's7': 'evidence', 's8': 'evidence', 's9': 'industry',
             's10': 'value', 's11': 'path', 's12': 'close'}

# ---- narration, one segment per scene ---------------------------------------
SEGMENTS = [
    ("s1", "AI is entering incident work. This is how a decision model, TypeSafe's Jev, could take "
           "on the repeated judgement calls inside operations."),
    ("s2", "Applications already interpret and coordinate. Observability platforms point to a root cause, "
           "service-management platforms organise the workflow, and cloud and network tools connect "
           "context to response. What is left is the decision."),
    ("s3", "Think end to end: an incident runs from Detect to Learn. Detection, execution and record-keeping "
           "are well automated. The links in the middle - is it real, whose is it, how bad, act or page - "
           "still fall to rules and to whoever is on call."),
    ("s4", "Jev answers fixed, typed questions about the context it is given. Choose from a list, place on "
           "a scale, or estimate whether a statement is true - each with a probability, in one call. The "
           "questions and the thresholds are yours; ordinary code decides."),
    ("s5", "Today an engineer reads the alert, checks the dashboards and logs, and judges. With a decision "
           "step, the platform sends the context to one call and gets the classification, the severity and "
           "a proposed action back, each with a probability."),
    ("s6", f"An example: a service becomes unreachable. {EX['id']} is a name-resolution failure. The model "
           f"reads it once, calls it a {EX['category']} incident, and the gate either permits an action or "
           f"sends it to a person - here it returned {EX['outcome']}."),
    ("s7", f"One request. The state sent is the alert and its context: the service or VIP, recent changes, "
           f"and the relevant log lines. Twelve questions come back with probabilities in about {P50} "
           f"milliseconds. The gate reads only the answers it needs."),
    ("s8", f"On {N} synthetic incidents, all four models worked. Jev matched the reference action on "
           f"{EXACT} of {N}, and the gate permitted action on {AUTO}, none of them unsafe. The point is "
           f"that a typed decision step works, not which model wins."),
    ("s9", "It integrates with the software already in place. ServiceNow, PagerDuty and F5 call the model at "
           "a decision point; a policy you own acts on the answer, or falls back to the rules you run today."),
    ("s10", "Why it is attractive: versatile across tasks, easier to configure than prompt engineering, low "
            f"cost at a fraction of a cent per incident, and fast, with the decision in your own code."),
    ("s11", "So: size the opportunity on a short diagnostic, replay closed tickets to see whether it beats "
            "what runs today, then run it in shadow and in assist mode - a decision after each stage."),
    ("s12", "AI in IT operations. Keep the tools you trust, add one decision layer, and find out on your "
            "own tickets. We would be glad to help."),
]


def tts(text: str, path: Path) -> None:
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}",
                   headers={"xi-api-key": EL_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                   json={"text": text, "model_id": "eleven_multilingual_v2",
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0,
                                            "use_speaker_boost": True, "speed": SPEED}}, timeout=180)
    if r.status_code != 200:
        raise SystemExit(f"TTS {r.status_code}: {r.text[:300]}")
    path.write_bytes(r.content)


def dur(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                                capture_output=True, text=True, check=True).stdout.strip())


def silence(path: Path, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", str(seconds), "-q:a", "9", str(path)], check=True)


def build_audio() -> list[float]:
    paths.DEMO_ASSETS.mkdir(parents=True, exist_ok=True)
    durations = []
    for sid, text in SEGMENTS:
        p = paths.DEMO_ASSETS / f"vo_{sid}.mp3"
        tts(text, p); d = dur(p); durations.append(d)
        print(f"  {sid}: {d:5.1f}s ({len(text.split())} words)")
    lead = paths.DEMO_ASSETS / "_lead.mp3"; tail = paths.DEMO_ASSETS / "_tail.mp3"
    silence(lead, LEAD); silence(tail, TAIL)
    parts = [lead] + [paths.DEMO_ASSETS / f"vo_{sid}.mp3" for sid, _ in SEGMENTS] + [tail]
    lf = paths.DEMO_ASSETS / "_concat.txt"
    lf.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lf),
                    "-c", "copy", str(paths.DEMO_ASSETS / "vo.mp3")], check=True)
    return durations


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden;background:#060912;color:#e8eef7;
  font-family:Inter,ui-sans-serif,system-ui,"Segoe UI",Arial,sans-serif}
#root{position:relative;width:100%;height:100%;overflow:hidden;background:#060912}
.mesh{position:absolute;inset:-20%;filter:blur(60px);opacity:.85}
.blob{position:absolute;border-radius:50%}
.b1{width:900px;height:900px;left:8%;top:-10%;background:radial-gradient(circle,#0e5b66,transparent 62%)}
.b2{width:800px;height:800px;right:0%;top:20%;background:radial-gradient(circle,#123a6b,transparent 62%)}
.b3{width:760px;height:760px;left:38%;bottom:-14%;background:radial-gradient(circle,#0a3b6b,transparent 62%)}
.grain{position:absolute;inset:0;background:#060912;opacity:.42}
.scene{position:absolute;inset:0;padding:70px 96px;display:flex;flex-direction:column;justify-content:center}
.center{align-items:center;text-align:center}
.kicker{font-size:15px;letter-spacing:.24em;color:#5eead4;font-weight:700;margin-bottom:18px}
.huge{font-size:96px;font-weight:800;letter-spacing:-.03em;line-height:1.02}
.huge .ch{display:inline-block}
.title{font-size:46px;font-weight:750;line-height:1.18;max-width:1660px}
.sub{font-size:22px;color:#9fb2cc;margin-top:16px}
.lede{font-size:22px;color:#b7c6dc;max-width:1200px;margin-top:24px;line-height:1.55}
.cards3{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;margin-top:38px}
.cards4{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:40px}
.card{background:rgba(14,22,38,.86);border:1px solid #1e3050;border-radius:18px;padding:26px 28px}
.card h3{font-size:22px;color:#eaf2fb;margin-bottom:10px}
.card p{font-size:16px;color:#a9bbd3;line-height:1.5}
.card .num{font-size:40px;font-weight:800;color:#5eead4}
.flow{display:flex;align-items:center;gap:14px;margin-top:44px;flex-wrap:wrap;justify-content:center}
.node{background:#0e1626;border:1px solid #24406a;border-radius:12px;padding:16px 20px;font-size:20px;min-width:150px;text-align:center}
.node.hot{border-color:#5eead4;box-shadow:0 0 0 3px rgba(94,234,212,.18);color:#c9fff6}
.arw{color:#38bdf8;font-size:26px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:34px}
.col{background:rgba(14,22,38,.72);border:1px solid #1e3050;border-radius:18px;padding:28px}
.col h3{font-size:22px;margin-bottom:12px}
.col.now h3{color:#f8a5a5}.col.after h3{color:#8ef0cf}
.col p{font-size:17px;color:#b7c6dc;line-height:1.55}
.rows{margin-top:26px}
.row{display:grid;grid-template-columns:280px 1fr 120px;gap:16px;align-items:center;padding:9px 0;border-bottom:1px solid #17233a;font-size:17px}
.row b{font-weight:700}
.bar{grid-column:2/4;height:9px;background:#17233a;border-radius:5px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#38bdf8,#5eead4)}
.rchart{display:flex;flex-direction:column;gap:18px;margin-top:30px}
.rrow{display:grid;grid-template-columns:260px 1fr 150px;gap:18px;align-items:center;font-size:19px}
.rbar{height:26px;background:#0e1626;border:1px solid #24406a;border-radius:8px;overflow:hidden}
.rbar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#0ea5a5,#5eead4)}
.net{position:relative;height:340px;margin-top:30px}
.nbox{position:absolute;background:#0e1626;border:1px solid #24406a;border-radius:12px;padding:14px 18px;font-size:18px;text-align:center}
.done{opacity:.45}
.stats{display:flex;gap:70px;margin-top:48px}
.stat .num{font-size:64px;font-weight:800;color:#5eead4}
.stat .lab{font-size:16px;color:#9fb2cc;margin-top:6px}
.stages{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin-top:40px}
.stage{background:rgba(14,22,38,.8);border:1px solid #1e3050;border-radius:16px;padding:24px}
.stage .n{font-size:13px;letter-spacing:.16em;color:#5eead4;font-weight:700}
.stage h3{font-size:20px;margin:8px 0 8px}
.stage p{font-size:15px;color:#a9bbd3;line-height:1.5}
.bgstage{position:absolute;inset:0;z-index:0;overflow:hidden;background:#060912}
.bgimg{position:absolute;inset:-5%;background-size:cover;background-position:center;opacity:0;
  transform-origin:center;will-change:opacity,transform}
.bgveil{position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,9,18,.5) 0%,rgba(6,9,18,.8) 62%,rgba(6,9,18,.96) 100%)}
.flash{position:absolute;inset:0;background:#eafcff;opacity:0;z-index:6;pointer-events:none}
.mesh{z-index:0;opacity:.4}
.scene{z-index:1}
"""


def s1():
    return f"""<section class="scene center" id="s1"><div class="kicker">IT OPERATIONS · DEMO</div>
      <h1 class="huge" data-split>AI in IT operations</h1>
      <p class="sub">The emerging role of a decision model</p></section>"""


def s2():
    items = [("Interpret", "Dynatrace's Davis points to a root cause; Datadog's Bits AI SRE investigates."),
             ("Coordinate", "ServiceNow agents assign, analyse and verify the work."),
             ("Connect", "AWS DevOps Agent and F5 bring telemetry, code and device context together.")]
    cards = "".join(f'<div class="card sc"><h3>{h}</h3><p>{b}</p></div>' for h, b in items)
    return f"""<section class="scene" id="s2"><div class="kicker">THE INDUSTRY</div>
      <h2 class="title">AI is entering incident work, one capability at a time</h2>
      <div class="cards3">{cards}</div></section>"""


def s3():
    steps = ["Detect", "Interpret", "Direct", "Respond", "Learn"]
    nodes = ""
    for i, st in enumerate(steps):
        hot = " hot" if st == "Interpret" else ""
        nodes += f'<span class="node{hot} sc">{st}</span>'
        if i < len(steps) - 1:
            nodes += '<span class="arw sc">→</span>'
    return f"""<section class="scene" id="s3"><div class="kicker">THE GAP</div>
      <h2 class="title">The cycle runs Detect to Learn; the decision step is the least mature</h2>
      <div class="flow">{nodes}</div>
      <p class="lede sc">Detection, execution and record-keeping are well automated. The links in the middle - is it real, whose is it, how bad, act or page - still fall to rules and the on-call engineer.</p></section>"""


def s4():
    items = [("Choice", "Pick one option from a list."), ("Score", "Place the state on a scale."),
             ("Noul", "The probability a statement is true.")]
    cards = "".join(f'<div class="card sc"><h3>{h}</h3><p>{b}</p></div>' for h, b in items)
    return f"""<section class="scene" id="s4"><div class="kicker">A DECISION MODEL</div>
      <h2 class="title">Fixed questions in, answers with probabilities out - one call</h2>
      <div class="cards3">{cards}</div>
      <p class="lede sc">The questions and the thresholds are yours; ordinary code compares the probabilities and decides what happens.</p></section>"""


def s5():
    return f"""<section class="scene" id="s5"><div class="kicker">BEFORE AND AFTER</div>
      <h2 class="title">How this looks today, by hand - and with a decision step</h2>
      <div class="split">
        <div class="col now sc"><h3>Today, by hand</h3><p>An engineer reads the alert, opens the dashboards and logs, looks for a recent change, and judges whether to act. Minutes to hours, and it depends on who is on call.</p></div>
        <div class="col after sc"><h3>With a decision step</h3><p>One call returns the classification, the severity and a proposed action, each with a probability. Your code acts, asks a person, or logs - the same questions, every time.</p></div>
      </div></section>"""


def s6():
    rows = [("Is this real?", f"{EX['real']:.2f}"), ("Category", EX["category"]),
            ("Root cause", EX["root"]), ("Severity (0-3)", f"{EX['severity']:.2f}"),
            ("Proposed action", EX["action"]), ("Page a person?", f"{EX['page']:.2f}")]
    rh = "".join(f'<div class="row sc"><b>{k}</b><span>{v}</span><span></span></div>' for k, v in rows)
    return f"""<section class="scene" id="s6"><div class="kicker">AN EXAMPLE</div>
      <h2 class="title">A service becomes unreachable - read once, classified, gated</h2>
      <div class="split">
        <div class="col sc"><h3>{EX['id']} · name resolution</h3><p style="margin-bottom:14px">A service cannot be reached; checks point at a name-resolution failure.</p>
          <div class="net">
            <div class="nbox" style="left:0;top:40px">Client</div>
            <div class="nbox" style="left:330px;top:40px">F5 VIP</div>
            <div class="nbox" style="left:660px;top:40px">Pool</div>
            <div class="nbox pk" style="left:330px;top:180px">DNS ✕</div>
          </div></div>
        <div class="col sc"><h3>Answers and gate</h3><div class="rows">{rh}</div>
          <p style="margin-top:14px;color:#8ef0cf;font-weight:700">Outcome: {EX['outcome']} · nothing executed</p></div>
      </div></section>"""


def s7():
    return f"""<section class="scene center" id="s7"><div class="kicker">ONE REQUEST</div>
      <div class="stats">
        <div class="stat sc"><div class="num" data-count="12">0</div><div class="lab">typed questions</div></div>
        <div class="stat sc"><div class="num" data-count="{P50}" data-suffix=" ms">0</div><div class="lab">median latency</div></div>
        <div class="stat sc"><div class="num" data-count="1">0</div><div class="lab">API call</div></div>
      </div>
      <p class="lede sc">The state sent is the alert and its context - the service or VIP, recent changes, and the relevant log lines. The gate reads only the answers it needs.</p></section>"""


def s8():
    order = [("Jev", "jev_native"), ("OpenRouter", "jev_openrouter"), ("Kev-4B", "kev"), ("Laya", "laya_local")]
    rows = ""
    for label, key in order:
        b = FACTS["backends"][key]
        pct = round(b["action_exact"]["pct"])
        rows += (f'<div class="rrow sc"><span>{label}</span>'
                 f'<span class="rbar"><i data-w="{pct}"></i></span>'
                 f'<span>exact {pct}% · auto {b["auto"]}/{N}</span></div>')
    return f"""<section class="scene" id="s8"><div class="kicker">THE EVIDENCE</div>
      <h2 class="title">All four models worked; the differences are modest</h2>
      <div class="rchart">{rows}</div>
      <p class="lede sc">Every model answered sensibly, and none automated a case labelled unsafe. The point is that a typed decision step works - not which model wins.</p></section>"""


def s9():
    nodes = ['<span class="node sc">F5 · Datadog · ServiceNow</span>', '<span class="arw sc">→</span>',
             '<span class="node hot sc">Jev</span>', '<span class="arw sc">→</span>',
             '<span class="node sc">Policy in your code</span>', '<span class="arw sc">→</span>',
             '<span class="node sc">Assign · investigate · runbook</span>']
    return f"""<section class="scene" id="s9"><div class="kicker">INTEGRATION</div>
      <h2 class="title">It integrates with the software you already run</h2>
      <div class="flow">{''.join(nodes)}</div>
      <p class="lede sc">A business rule or flow calls the model; a policy you own acts on the answer, and falls back to the rules that run today on timeout or low confidence.</p></section>"""


def s10():
    items = [("Versatile", "Classification, severity, routing and yes/no checks - across application and network incidents."),
             ("Easy to configure", "Questions and thresholds in code; no prompt engineering, no training to start."),
             ("Low cost", "A fraction of a cent of inference per incident."),
             ("Fast and owned", "Milliseconds per call, and the decision stays in your code.")]
    cards = "".join(f'<div class="card sc"><h3>{h}</h3><p>{b}</p></div>' for h, b in items)
    return f"""<section class="scene" id="s10"><div class="kicker">THE VALUE</div>
      <h2 class="title">Why a decision model is attractive</h2>
      <div class="cards4">{cards}</div></section>"""


def s11():
    stages = [("STAGE 1", "Diagnostic", "Baseline reassignment, triage and out-of-hours volume. Decision: is there a gap worth closing?"),
              ("STAGE 2", "Offline replay", "2,000-5,000 closed tickets, compared with current rules. Decision: does it beat what runs today?"),
              ("STAGE 3", "Shadow, then assist", "No actions, then suggestions with override tracking. Decision: what autonomy, under which owner?")]
    cards = "".join(f'<div class="stage sc"><div class="n">{n}</div><h3>{h}</h3><p>{b}</p></div>' for n, h, b in stages)
    return f"""<section class="scene" id="s11"><div class="kicker">THE PATH</div>
      <h2 class="title">How to explore this together: size it, then a staged pilot</h2>
      <div class="stages">{cards}</div></section>"""


def s12():
    return f"""<section class="scene center" id="s12"><div class="kicker">IN SUMMARY</div>
      <h1 class="huge" data-split>Keep the tools. Add a decision layer.</h1>
      <p class="lede sc">Find out on your own tickets. We would be glad to help.</p></section>"""


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12]


def build_html(durations: list[float]) -> str:
    starts, acc = [], LEAD
    for d in durations:
        starts.append(acc); acc += d
    total = acc + TAIL
    scenes = [{"id": sid, "start": round(starts[i], 3), "end": round(starts[i] + durations[i], 3)}
              for i, (sid, _) in enumerate(SEGMENTS)]
    body = "".join(fn() for fn in SCENES)
    bgs = "".join(f'<div class="bgimg" id="bg_{sid}" style="background-image:url(assets/img_{SCENE_IMG[sid]}.png)"></div>'
                  for sid, _ in SEGMENTS)
    js = f"""
const SCENES = {json.dumps(scenes)};
const tl = gsap.timeline({{ paused: true }});
tl.set(".scene", {{ autoAlpha: 0 }});
tl.fromTo(".b1", {{ x: -60, y: -30 }}, {{ x: 60, y: 40, duration: {total:.2f}, ease: "none" }}, 0);
tl.fromTo(".b2", {{ x: 40 }}, {{ x: -80, y: 40, duration: {total:.2f}, ease: "none" }}, 0);
tl.fromTo(".b3", {{ y: 40 }}, {{ y: -50, x: 40, duration: {total:.2f}, ease: "none" }}, 0);
// per-character title reveal targets
function anim(sel, from, to, pos) {{
  const els = document.querySelectorAll(sel);
  if (els.length) tl.fromTo(els, from, to, pos);
}}
SCENES.forEach((sc, i) => {{
  const q = (suffix) => "#" + sc.id + suffix;
  const bg = "#bg_" + sc.id;
  tl.fromTo(bg, {{ opacity: 0 }}, {{ opacity: 0.55, duration: 0.9, ease: "power1.out" }}, sc.start - 0.15);
  tl.fromTo(bg, {{ scale: 1.06 }}, {{ scale: 1.15, duration: (sc.end - sc.start) + 0.9, ease: "none" }}, sc.start - 0.15);
  tl.to(bg, {{ opacity: 0, duration: 0.7 }}, sc.end - 0.7);
  if (i < SCENES.length - 1) {{
    tl.fromTo("#flash", {{ opacity: 0 }}, {{ opacity: 0.22, duration: 0.16 }}, sc.end - 0.16);
    tl.to("#flash", {{ opacity: 0, duration: 0.2 }}, sc.end + 0.02);
  }}
  anim(q(""), {{ autoAlpha: 0 }}, {{ autoAlpha: 1, duration: 0.5 }}, sc.start);
  anim(q(" .ch"), {{ autoAlpha: 0, y: 60, rotation: 4 }},
       {{ autoAlpha: 1, y: 0, rotation: 0, stagger: 0.05, duration: 0.6, ease: "power3.out" }}, sc.start + 0.25);
  anim(q(" .title"), {{ autoAlpha: 0, y: 30 }}, {{ autoAlpha: 1, y: 0, duration: 0.6, ease: "power2.out" }}, sc.start + 0.2);
  anim(q(" .kicker"), {{ autoAlpha: 0, y: -14 }}, {{ autoAlpha: 1, y: 0, duration: 0.5 }}, sc.start + 0.1);
  anim(q(" .sub"), {{ autoAlpha: 0, y: 16 }}, {{ autoAlpha: 1, y: 0, duration: 0.6 }}, sc.start + 0.7);
  anim(q(" .lede"), {{ autoAlpha: 0, y: 16 }}, {{ autoAlpha: 1, y: 0, duration: 0.6 }}, sc.start + 0.7);
  anim(q(" .card, " + q(" .col, ") + q(" .node, ") + q(" .stage, ") + q(" .stat, ") + q(" .rrow")),
       {{ autoAlpha: 0, y: 26, scale: 0.94 }},
       {{ autoAlpha: 1, y: 0, scale: 1, stagger: 0.12, duration: 0.5, ease: "power2.out" }}, sc.start + 0.6);
  anim(q(" .arw"), {{ autoAlpha: 0 }}, {{ autoAlpha: 1, stagger: 0.1, duration: 0.3 }}, sc.start + 0.9);
  // counters
  document.querySelectorAll("#"+sc.id+" [data-count]").forEach(el => {{
    const target = Number(el.getAttribute("data-count"));
    const suffix = el.getAttribute("data-suffix") || "";
    const o = {{ v: 0 }};
    tl.to(o, {{ v: target, duration: 1.1, ease: "power1.out",
      onUpdate: () => {{ el.textContent = Math.round(o.v) + suffix; }} }}, sc.start + 0.9);
  }});
  // bars
  document.querySelectorAll("#"+sc.id+" .rbar>i, #"+sc.id+" .bar>i").forEach(el => {{
    tl.to(el, {{ width: (el.getAttribute("data-w") || "0") + "%", duration: 0.9, ease: "power2.out" }}, sc.start + 0.9);
  }});
  // network packet travels then fails
  if (sc.id === "s6") tl.fromTo("#s6 .pk", {{ autoAlpha: 0, y: -60 }},
              {{ autoAlpha: 1, y: 0, duration: 0.6, ease: "power2.in" }}, sc.start + 1.0);
  if (i < SCENES.length - 1) tl.to("#"+sc.id, {{ autoAlpha: 0, duration: 0.45 }}, sc.end - 0.45);
}});
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
tl.seek(0);
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=1920, height=1080"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.2f}" data-fps="30"
     data-width="1920" data-height="1080" data-layout-allow-overlap data-layout-allow-occlusion>
  <div class="bgstage">{bgs}<div class="bgveil"></div></div>
  <div class="flash"></div>
  <div class="mesh"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
  <div class="grain"></div>
  <audio id="vo" class="clip" data-start="0" data-duration="{total:.2f}" data-track-index="9" data-volume="1" src="assets/vo.mp3"></audio>
  {body}
</div>
<script>
// split headings into characters
document.querySelectorAll("[data-split]").forEach(el => {{
  el.innerHTML = [...el.textContent].map(c => c === " " ? "<span class=\\"ch\\">&nbsp;</span>" : `<span class="ch">${{c}}</span>`).join("");
}});
{js}
</script>
</body></html>
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    if dry:
        for sid, text in SEGMENTS:
            print(f"{sid}: {len(text.split())} words")
        print(f"{len(SEGMENTS)} segments; ~{sum(len(t.split()) for _, t in SEGMENTS)/2.5:.0f}s of speech")
        return 0
    if not EL_KEY:
        raise SystemExit("ELEVENLABS_API not set in .env")
    print(f"voice={VOICE} speed={SPEED}")
    durations = build_audio()
    total = sum(durations) + LEAD + TAIL
    paths.DEMO_SRC.mkdir(parents=True, exist_ok=True)
    paths.DEMO_PAGE.write_text(build_html(durations))
    (paths.RESULTS / "demo_segments.json").write_text(
        json.dumps({"voice": VOICE, "speed": SPEED, "total": round(total, 2),
                    "segments": [{"id": s, "dur": round(d, 2)} for (s, _), d in zip(SEGMENTS, durations)]}, indent=2))
    print(f"\ntotal: {sum(durations):.1f}s + lead/tail = {total:.1f}s ({total/60:.1f} min)")
    print(f"wrote {paths.rel(paths.DEMO_PAGE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
