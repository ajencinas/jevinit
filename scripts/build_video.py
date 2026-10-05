#!/usr/bin/env python3
"""Build the single narrated demo video (work/video/showcase -> outputs/4_demo.mp4).

A technical explainer: one call, typed answers, the gate in code, a worked network example and the
limits. On-screen text is deliberately minimal (few labels; the narration carries the message, not
a readout of the data). No commercial close and no summary. Visuals are HyperFrames-native: GSAP,
an animated mesh, crossfading generated backgrounds, kinetic titles, a gate with real margins.

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
N = FACTS["n"]
P50 = round(NAT["p50_ms"])
EXACT, EXACT_PCT = NAT["action_exact"]["k"], round(NAT["action_exact"]["pct"])


def network_example() -> dict:
    recs = [json.loads(l) for l in paths.decisions("jev_native").read_text().splitlines() if l.strip()]
    r = next((x for x in recs if x["archetype"] == "dns_failure"), recs[0])
    p = r["pred"]
    return {"id": r["incident_id"], "outcome": r["decision"]["outcome"],
            "real": p["real_incident"], "category": p["failure_category"],
            "root": p["root_cause"], "severity": p["severity"], "action": p["proposed_action"],
            "page": p["needs_page"], "risk": p["action_risk"],
            "action_conf": p["action_confidence"]}


EX = network_example()
SCENE_IMG = {"s1": "hero", "s2": "jev", "s3": "industry", "s4": "value", "s5": "gap",
             "s6": "evidence", "s7": "example", "s8": "example", "s9": "industry"}

# ---- narration: technical, one message per scene ----------------------------
SEGMENTS = [
    ("s1", "One call, typed answers, and a gate in code. This is how a decision model answers an "
           "incident question, and where the control sits."),
    ("s2", "A generative model returns text that you then parse, and the schema can break. A decision "
           "model returns a typed answer. One request, many questions, a probability on each."),
    ("s3", "The request carries a state - the alert and its context - and a fixed set of typed "
           "questions. The model evaluates them in a single pass and returns one typed answer per "
           "question. It does not generate text."),
    ("s4", "There are three question types. Choice picks one option from a list. Score places the "
           "state on an ordered scale. Noul returns the probability that a statement is true. All of "
           "them run in parallel against the same state."),
    ("s5", "What is sent is the alert text and its enrichment: the service, the recent change, the "
           "log line. What comes back is a typed answer and a probability for each question. There "
           "is nothing to parse."),
    ("s6", "The gate is ordinary code, not the model. It reads only the answers it needs, compares "
           "them with thresholds you own, and fails closed: a missing or malformed answer escalates "
           "rather than passing."),
    ("s7", f"One incident: name resolution fails, so a service is unreachable. The model classified "
           f"it, proposed an action, and the gate permitted it. It cleared the paging check by two "
           f"hundredths of a point, against a cut-off of 0.90."),
    ("s8", "The model is not the security boundary. Text it is given can be attacker-influenced, "
           "option order changes answers, and it cannot do arithmetic or dates. So permissions, "
           "approvals and reversibility stay in code."),
    ("s9", "The shape is a cascade: deterministic rules first, the decision model for the semantic "
           "call, and a generative model only when the decision is genuinely uncertain. The gate "
           "stays in code, and every answer is logged with its probability."),
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
.bgstage{position:absolute;inset:0;z-index:0;overflow:hidden;background:#060912}
.bgimg{position:absolute;inset:-5%;background-size:cover;background-position:center;opacity:0;transform-origin:center;will-change:opacity,transform}
.bgveil{position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,9,18,.55) 0%,rgba(6,9,18,.82) 60%,rgba(6,9,18,.96) 100%)}
.flash{position:absolute;inset:0;background:#eafcff;opacity:0;z-index:6;pointer-events:none}
.mesh{position:absolute;inset:-20%;filter:blur(60px);z-index:0;opacity:.4}
.blob{position:absolute;border-radius:50%}
.b1{width:900px;height:900px;left:8%;top:-10%;background:radial-gradient(circle,#0e5b66,transparent 62%)}
.b2{width:800px;height:800px;right:0%;top:20%;background:radial-gradient(circle,#123a6b,transparent 62%)}
.b3{width:760px;height:760px;left:38%;bottom:-14%;background:radial-gradient(circle,#0a3b6b,transparent 62%)}
.grain{position:absolute;inset:0;background:#060912;opacity:.42;z-index:0}
.scene{position:absolute;inset:0;padding:80px 110px;display:flex;flex-direction:column;justify-content:center;z-index:1}
.center{align-items:center;text-align:center}
.kicker{font-size:15px;letter-spacing:.24em;color:#5eead4;font-weight:700;margin-bottom:18px}
.huge{font-size:92px;font-weight:800;letter-spacing:-.03em;line-height:1.04}
.huge .ch{display:inline-block}
.title{font-size:52px;font-weight:750;line-height:1.14;max-width:1640px}
.sub{font-size:24px;color:#9fb2cc;margin-top:18px}
.diagram{display:flex;align-items:center;gap:22px;margin-top:60px;flex-wrap:wrap;justify-content:center}
.box{background:rgba(14,22,38,.9);border:1px solid #24406a;border-radius:14px;padding:20px 24px;font-size:22px;text-align:center;min-width:180px}
.box small{display:block;font-size:14px;color:#8ba3c4;margin-top:6px;font-weight:400}
.box.hot{border-color:#5eead4;box-shadow:0 0 0 3px rgba(94,234,212,.18);color:#c9fff6}
.arw{color:#38bdf8;font-size:30px}
.cards3{display:grid;grid-template-columns:repeat(3,1fr);gap:28px;margin-top:56px}
.card{background:rgba(14,22,38,.86);border:1px solid #1e3050;border-radius:18px;padding:30px 32px}
.card h3{font-size:30px;color:#eaf2fb;margin-bottom:10px}
.card p{font-size:18px;color:#a9bbd3;line-height:1.5}
.split{display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:44px}
.col{background:rgba(14,22,38,.8);border:1px solid #1e3050;border-radius:18px;padding:30px 32px}
.col h3{font-size:22px;color:#5eead4;margin-bottom:16px;letter-spacing:.04em;text-transform:uppercase}
.kv{display:flex;justify-content:space-between;padding:11px 0;border-bottom:1px solid #17233a;font-size:21px}
.kv span:last-child{color:#eaf2fb;font-weight:600}
.gate{margin-top:34px}
.grow{display:grid;grid-template-columns:420px 1fr 140px;gap:20px;align-items:center;padding:12px 0;border-bottom:1px solid #17233a;font-size:21px}
.gbar{height:10px;background:#17233a;border-radius:6px;overflow:hidden}
.gbar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#38bdf8,#5eead4)}
.ok{color:#34d399;font-weight:700}
.chips{display:flex;gap:18px;flex-wrap:wrap;margin-top:44px;justify-content:center}
.chip{background:rgba(14,22,38,.86);border:1px solid #24406a;border-radius:999px;padding:16px 26px;font-size:21px;color:#c2cee2}
.net{position:relative;height:300px;margin-top:8px}
.nbox{position:absolute;background:#0e1626;border:1px solid #24406a;border-radius:12px;padding:13px 18px;font-size:19px}
.nbox.done{opacity:.5}
.pk{color:#f8a5a5;border-color:#7f2b2b}
"""


def s1():
    return f"""<section class="scene center" id="s1"><div class="kicker">JEV · SYSTEM ONE DECISION MODEL</div>
      <h1 class="huge" data-split>One call, typed answers</h1>
      <p class="sub">and a gate that stays in code</p></section>"""


def s2():
    return f"""<section class="scene" id="s2"><div class="kicker">THE CONTRACT</div>
      <h2 class="title">Typed answers, not generated text</h2>
      <div class="split">
        <div class="col sc"><h3>Generative</h3>
          <div class="kv"><span>returns</span><span>text</span></div>
          <div class="kv"><span>then</span><span>you parse it</span></div>
          <div class="kv"><span>risk</span><span>schema breaks</span></div></div>
        <div class="col sc"><h3>Decision model</h3>
          <div class="kv"><span>state + questions in</span><span>typed answers out</span></div>
          <div class="kv"><span>plus</span><span>a probability each</span></div>
          <div class="kv"><span>schema</span><span>guaranteed</span></div></div>
      </div></section>"""


def s3():
    return f"""<section class="scene" id="s3"><div class="kicker">ONE REQUEST</div>
      <h2 class="title">State and typed questions in one call</h2>
      <div class="diagram">
        <span class="box sc">STATE<small>alert + context</small></span>
        <span class="arw sc">+</span>
        <span class="box sc">QUESTIONS<small>12, typed</small></span>
        <span class="arw sc">→</span>
        <span class="box hot sc">MODEL<small>single pass</small></span>
        <span class="arw sc">→</span>
        <span class="box sc">ANSWERS<small>typed + probabilities</small></span>
      </div></section>"""


def s4():
    return f"""<section class="scene" id="s4"><div class="kicker">THE PRIMITIVES</div>
      <h2 class="title">Three question types, one pass</h2>
      <div class="cards3">
        <div class="card sc"><h3>Choice</h3><p>Pick one option from a list.</p></div>
        <div class="card sc"><h3>Score</h3><p>Place the state on an ordered scale.</p></div>
        <div class="card sc"><h3>Noul</h3><p>The probability a statement is true.</p></div>
      </div></section>"""


def s5():
    return f"""<section class="scene" id="s5"><div class="kicker">THE CALL</div>
      <h2 class="title">What is sent, what comes back</h2>
      <div class="split">
        <div class="col sc"><h3>Sent (state)</h3>
          <div class="kv"><span>service</span><span>payment-svc</span></div>
          <div class="kv"><span>recent change</span><span>deploy 6 min before</span></div>
          <div class="kv"><span>log line</span><span>no such host</span></div></div>
        <div class="col sc"><h3>Returned (typed)</h3>
          <div class="kv"><span>real_incident</span><span>{EX['real']:.2f}</span></div>
          <div class="kv"><span>failure_category</span><span>{EX['category']}</span></div>
          <div class="kv"><span>proposed_action</span><span>{EX['action']}</span></div></div>
      </div></section>"""


def s6():
    rows = [("real_incident ≥ 0.50", f"{EX['real']:.2f}", 43),
            ("action confidence ≥ 0.60", f"{EX['action_conf']:.2f}", 19),
            ("needs_page < 0.90", f"{EX['page']:.2f}", 17)]
    rh = "".join(f'<div class="grow sc"><span>{k}</span>'
                 f'<span class="gbar"><i data-w="{w}"></i></span>'
                 f'<span class="ok">{v}</span></div>' for k, v, w in rows)
    return f"""<section class="scene" id="s6"><div class="kicker">THE GATE</div>
      <h2 class="title">The gate is ordinary code, not the model</h2>
      <div class="gate">{rh}
        <div class="grow sc" style="border:0"><span>missing answer</span>
          <span class="gbar"><i></i></span><span style="color:#f8a5a5;font-weight:700">ESCALATE</span></div></div></section>"""


def s7():
    return f"""<section class="scene" id="s7"><div class="kicker">AN EXAMPLE</div>
      <h2 class="title">Name resolution fails; the gate permits an action</h2>
      <div class="split">
        <div class="col sc" style="background:transparent;border:0;padding:0">
          <div class="net">
            <div class="nbox" style="left:0;top:30px">Client</div>
            <div class="nbox" style="left:300px;top:30px">F5 VIP</div>
            <div class="nbox done" style="left:600px;top:30px">Pool</div>
            <div class="nbox pk" style="left:300px;top:170px">DNS ✕</div>
          </div></div>
        <div class="col sc"><h3>Result</h3>
          <div class="kv"><span>root cause</span><span>{EX['root']}</span></div>
          <div class="kv"><span>needs_page</span><span>{EX['page']:.2f} &lt; 0.90</span></div>
          <div class="kv"><span>outcome</span><span style="color:#34d399">{EX['outcome']}</span></div>
          <div class="kv"><span>executed</span><span>nothing</span></div></div>
      </div></section>"""


def s8():
    chips = ["attacker-influenced text moves answers", "option order matters",
             "no arithmetic or dates", "fail closed on missing answers"]
    return f"""<section class="scene center" id="s8"><div class="kicker">THE BOUNDARY</div>
      <h2 class="title">The model is not the security boundary</h2>
      <div class="chips">{''.join(f'<span class="chip sc">{c}</span>' for c in chips)}</div>
      <p class="sub sc">permissions, approvals and reversibility stay in code</p></section>"""


def s9():
    return f"""<section class="scene" id="s9"><div class="kicker">THE SHAPE</div>
      <h2 class="title">A cascade, with the gate in code</h2>
      <div class="diagram">
        <span class="box sc">RULES<small>deterministic</small></span>
        <span class="arw sc">→</span>
        <span class="box hot sc">DECISION MODEL<small>semantic call</small></span>
        <span class="arw sc">→</span>
        <span class="box sc">GENERATIVE<small>only when uncertain</small></span>
      </div>
      <p class="sub sc">every answer logged with its probability</p></section>"""


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9]


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
function anim(sel, from, to, pos) {{
  const els = document.querySelectorAll(sel);
  if (els.length) tl.fromTo(els, from, to, pos);
}}
SCENES.forEach((sc, i) => {{
  const q = (suffix) => "#" + sc.id + suffix;
  const bg = "#bg_" + sc.id;
  tl.fromTo(bg, {{ opacity: 0 }}, {{ opacity: 0.5, duration: 0.9, ease: "power1.out" }}, sc.start - 0.15);
  tl.fromTo(bg, {{ scale: 1.06 }}, {{ scale: 1.15, duration: (sc.end - sc.start) + 0.9, ease: "none" }}, sc.start - 0.15);
  tl.to(bg, {{ opacity: 0, duration: 0.7 }}, sc.end - 0.7);
  anim(q(""), {{ autoAlpha: 0 }}, {{ autoAlpha: 1, duration: 0.5 }}, sc.start);
  anim(q(" .ch"), {{ autoAlpha: 0, y: 60, rotation: 4 }},
       {{ autoAlpha: 1, y: 0, rotation: 0, stagger: 0.05, duration: 0.6, ease: "power3.out" }}, sc.start + 0.25);
  anim(q(" .title"), {{ autoAlpha: 0, y: 30 }}, {{ autoAlpha: 1, y: 0, duration: 0.6, ease: "power2.out" }}, sc.start + 0.2);
  anim(q(" .kicker"), {{ autoAlpha: 0, y: -14 }}, {{ autoAlpha: 1, y: 0, duration: 0.5 }}, sc.start + 0.1);
  anim(q(" .sub"), {{ autoAlpha: 0, y: 16 }}, {{ autoAlpha: 1, y: 0, duration: 0.6 }}, sc.start + 0.7);
  anim(q(" .card, ") + q(" .col, ") + q(" .box, ") + q(" .chip, ") + q(" .kv, ") + q(" .grow, ") + q(" .nbox"),
       {{ autoAlpha: 0, y: 24, scale: 0.96 }},
       {{ autoAlpha: 1, y: 0, scale: 1, stagger: 0.1, duration: 0.5, ease: "power2.out" }}, sc.start + 0.55);
  anim(q(" .arw"), {{ autoAlpha: 0 }}, {{ autoAlpha: 1, stagger: 0.1, duration: 0.3 }}, sc.start + 0.9);
  document.querySelectorAll(q(" .gbar>i")).forEach(el => {{
    tl.to(el, {{ width: (el.getAttribute("data-w") || "0") + "%", duration: 0.9, ease: "power2.out" }}, sc.start + 0.9);
  }});
  if (sc.id === "s7") tl.fromTo("#s7 .pk", {{ autoAlpha: 0, y: -50 }}, {{ autoAlpha: 1, y: 0, duration: 0.6, ease: "power2.in" }}, sc.start + 1.0);
  if (i < SCENES.length - 1) {{
    tl.to(q(""), {{ autoAlpha: 0, duration: 0.3, ease: "power1.in" }}, sc.end - 0.3);
    tl.fromTo("#flash", {{ opacity: 0 }}, {{ opacity: 0.22, duration: 0.16 }}, sc.end - 0.16);
    tl.to("#flash", {{ opacity: 0, duration: 0.2 }}, sc.end + 0.02);
  }}
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
document.querySelectorAll("[data-split]").forEach(el => {{
  el.innerHTML = [...el.textContent].map(c => c === " " ? "<span class=\\"ch\\">&nbsp;</span>" : `<span class="ch">${{c}}</span>`).join("");
}});
{js}
</script>
</body></html>
"""


def main() -> int:
    if "--dry-run" in sys.argv:
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
