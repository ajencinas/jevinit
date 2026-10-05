#!/usr/bin/env python3
"""Build "One incident, two kinds of output" (outputs/one-incident/index.html).

Default: rebuild the page from the recorded trace in work/results/race_trace.json. No network.

  ./jev/bin/python scripts/build_race.py

--live re-records the trace: one Jev call through OpenRouter's System One API and one chat
model call through OpenRouter chat/completions (strict JSON schema, temperature 0, not
streamed), on the same incident. Together they cost well under $0.001. The trace and page are
overwritten only if both calls succeed.

  ./jev/bin/python scripts/build_race.py --live [--incident INC-0001] [--chat-model openai/gpt-4o-mini]

The page shows one call each (n=1). It is about the shape of what comes back, a probability per
answer versus values only, and makes no claim about which model is faster or more accurate.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops.corpus import corpus_fingerprint, generate_corpus  # noqa: E402
from zeroops.paths import ENV, FACTS, HUB, ONE_INCIDENT_DIR, ONE_INCIDENT_PAGE as OUT, RACE_TRACE as TRACE  # noqa: E402
from zeroops.paths import decisions, href, rel  # noqa: E402
from zeroops.policy import decide, explain  # noqa: E402
from zeroops.schema import incident_questions  # noqa: E402

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

CHAT_FIELDS = {
    "real_incident": {"type": "boolean"},
    "failure_category": {"type": "string"},
    "root_cause": {"type": "string"},
    "severity": {"type": "integer"},
    "action": {"type": "string"},
}
CHAT_SCHEMA = {
    "type": "object",
    "properties": CHAT_FIELDS,
    "required": list(CHAT_FIELDS),
    "additionalProperties": False,
}
CHAT_SYSTEM = ("You are an SRE triage assistant. Return ONLY a JSON object with keys "
               "real_incident (bool), failure_category (string), root_cause (string), "
               "severity (0-3 int), action (string). Decide from the incident state.")


# --- live calls (only with --live) ------------------------------------------------------

def jev_call(state: str) -> dict:
    from zeroops.adapters import openrouter_adapter

    res = openrouter_adapter().decide(state, incident_questions())
    out = {"ok": res.ok, "ms": round(res.latency_ms, 1), "cost": res.cost_usd,
           "model": res.model, "provider": res.provider,
           "endpoint": "OpenRouter /api/v1/systemone",
           "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
           "error": res.error}
    if not res.ok:
        return out
    keep = ("type", "choice", "score", "noul", "confidence", "probabilities")
    raw = res.raw.get("answers") or {}
    out["answers"] = {q: {k: v for k, v in (raw.get(q) or {}).items() if k in keep}
                      for q in incident_questions()}
    out["missing"] = res.parsed.missing
    d = decide(res.parsed)
    out["gate"] = {"outcome": d.outcome, "action": d.action, "rationale": d.rationale,
                   "checks": explain(res.parsed)}
    return out


def chat_call(state: str, model: str, key: str) -> dict:
    import httpx

    body = {
        "model": model,
        "messages": [{"role": "system", "content": CHAT_SYSTEM},
                     {"role": "user", "content": json.dumps(
                         {"incident": state, "questions": incident_questions()}, indent=1)}],
        "temperature": 0,
        "stream": False,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "triage", "strict": True, "schema": CHAT_SCHEMA}},
    }
    request = {"fields": list(CHAT_FIELDS), "temperature": 0, "stream": False,
               "response_format": "json_schema (strict)", "system": CHAT_SYSTEM}
    t0 = time.perf_counter()
    try:
        r = httpx.post(CHAT_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
    except httpx.HTTPError as e:
        return {"ok": False, "ms": round((time.perf_counter() - t0) * 1000, 1), "error": repr(e)}
    ms = round((time.perf_counter() - t0) * 1000, 1)
    if r.status_code != 200:
        return {"ok": False, "ms": ms, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    try:
        j = r.json()
    except ValueError:
        return {"ok": False, "ms": ms, "error": f"non-JSON 200 body: {r.text[:200]}"}
    content = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content:
        return {"ok": False, "ms": ms, "error": "200 response without message content"}
    usage = j.get("usage") or {}
    parsed, perr = None, None
    try:
        parsed = json.loads(content)
    except ValueError as e:
        perr = repr(e)
    return {
        "ok": True, "ms": ms, "cost": usage.get("cost"),
        "model": j.get("model"), "provider": j.get("provider"), "request": request,
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
        "content": content, "parsed": parsed, "parse_error": perr, "error": None,
    }


def record(incident_id: str, chat_model: str) -> int:
    from dotenv import load_dotenv

    load_dotenv(ENV)
    key = os.getenv("OPENROUTER_API") or os.getenv("OPENROUTER_API_KEY") or ""
    if not key:
        print("OPENROUTER_API is not set; nothing recorded", file=sys.stderr)
        return 2
    corpus = generate_corpus(n_variants=4)
    inc = next(i for i in corpus if i.id == incident_id)
    print(f"recording {inc.id} ({inc.archetype}); chat model {chat_model}")
    jev = jev_call(inc.state)
    print(f"  Jev:  ok={jev['ok']} {jev.get('ms')} ms cost={jev.get('cost')} error={jev.get('error')}")
    chat = chat_call(inc.state, chat_model, key)
    print(f"  chat: ok={chat['ok']} {chat.get('ms')} ms cost={chat.get('cost')} error={chat.get('error')}")
    if not (jev["ok"] and chat["ok"]):
        print(f"not overwriting {TRACE.name}: a call failed", file=sys.stderr)
        return 1
    trace = {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus_version": corpus_fingerprint(corpus),
        "incident": {"id": inc.id, "archetype": inc.archetype, "state": inc.state,
                     "ground_truth": inc.ground_truth},
        "jev": jev, "chat": chat, "chat_model": chat_model,
    }
    TRACE.write_text(json.dumps(trace, indent=2))
    print(f"wrote {rel(TRACE)}")
    return 0


# --- page (from the trace) --------------------------------------------------------------

def _e(x) -> str:
    return html.escape(str(x))


def _date(iso: str | None) -> str:
    if not iso:
        return "date not recorded"
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}, {d.strftime('%H:%M')} UTC"


def openrouter_rate() -> float | None:
    """Per-input-token price implied by the 56 billed OpenRouter calls, if it is one flat rate."""
    f = decisions("jev_openrouter")
    if not f.exists():
        return None
    rates = []
    for line in f.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("cost_usd") and r.get("input_tokens"):
                rates.append(r["cost_usd"] / r["input_tokens"])
    if not rates or (max(rates) - min(rates)) / max(rates) > 0.01:
        return None
    return sum(rates) / len(rates)


def answer_rows(answers: dict) -> str:
    rows = []
    for q, a in answers.items():
        t = a.get("type", "")
        if t == "noul":
            v, p, pl = f"{a['noul']:.2f}", f"{a['noul']:.2f}", "P(yes)"
        elif t == "choice":
            v, p, pl = a["choice"], f"{a.get('confidence', 0):.2f}", "P(this choice)"
        else:
            n = len(incident_questions()[q]["criteria"]) - 1
            v, p, pl = f"{a['score']:.2f} on 0–{n}", f"{a.get('confidence', 0):.2f}", "P(nearest level)"
        rows.append(f"<tr><td>{_e(q)}</td><td class='t'>{_e(t)}</td><td><b>{_e(v)}</b></td>"
                    f"<td class='num'>{p}</td><td class='t m'>{pl}</td></tr>")
    return "".join(rows)


def gate_rows(checks: list[dict]) -> str:
    out = []
    for c in checks:
        cls = "pass" if c["passed"] else "fail"
        close = " <span class='close'>close</span>" if c["passed"] and abs(c["margin"]) <= 0.05 else ""
        out.append(f"<tr><td>{_e(c['check'])} {_e(c['op'])} {c['threshold']:g}</td>"
                   f"<td class='num'>{c['value']:.2f}</td><td class='{cls}'>"
                   f"{'PASS' if c['passed'] else 'FAIL'}{close}</td>"
                   f"<td class='num'>{c['margin']:+.2f}</td></tr>")
    return "".join(out)


def agreement(jev: dict, chat: dict) -> tuple[str, int, int]:
    a, c = jev["answers"], chat.get("parsed") or {}
    pairs = [
        ("real incident?", "yes" if a["real_incident"]["noul"] >= 0.5 else "no",
         f"{a['real_incident']['noul']:.2f}",
         None if "real_incident" not in c else ("yes" if c["real_incident"] else "no")),
        ("failure category", a["failure_category"]["choice"], "", c.get("failure_category")),
        ("root cause", a["root_cause"]["choice"], "", c.get("root_cause")),
        ("severity (0–3)", str(round(a["severity"]["score"])), f"{a['severity']['score']:.2f}",
         None if c.get("severity") is None else str(c["severity"])),
        ("first action", a["proposed_action"]["choice"], "", c.get("action")),
    ]
    rows, same = [], 0
    for name, jv, jraw, cv in pairs:
        ok = cv is not None and str(cv) == jv
        same += ok
        raw = f" <span class='t'>({jraw})</span>" if jraw else ""
        rows.append(f"<tr><td>{name}</td><td><b>{_e(jv)}</b>{raw}</td><td><b>{_e(cv if cv is not None else '—')}</b></td>"
                    f"<td class='{'pass' if ok else 'fail'}'>{'same' if ok else 'different'}</td></tr>")
    return "".join(rows), same, len(pairs)


def build_page(trace: dict) -> str:
    facts = json.loads(FACTS.read_text())
    jev, chat, inc = trace["jev"], trace["chat"], trace["incident"]
    orb = facts["backends"].get("jev_openrouter", {})
    rows, same, n_pairs = agreement(jev, chat)
    agree_text = (f"On this incident they gave the same answer on all {n_pairs} fields both were asked."
                  if same == n_pairs else
                  f"On this incident they agreed on {same} of the {n_pairs} fields both were asked.")
    rate = openrouter_rate()
    if rate and jev.get("cost") and abs(jev["cost"] - rate * jev["input_tokens"]) <= 0.02 * jev["cost"]:
        billing = (f"Billed ${jev['cost']:.6f}: the {jev['input_tokens']:,} input tokens at "
                   f"${rate * 1e6:.3f} per million, the same flat rate as all 56 calls in the evaluation run. "
                   f"The usage block also reports {jev['output_tokens']} output tokens; they were not billed.")
    else:
        billing = (f"Billed ${jev.get('cost') or 0:.6f}. The usage block reports {jev['input_tokens']:,} input "
                   f"and {jev['output_tokens']} output tokens.")
    g = jev["gate"]
    chat_parse = ("<span class='badge ok'>parsed as JSON</span>" if chat.get("parsed") is not None
                  else f"<span class='badge no'>not valid JSON</span> <span class='t'>{_e(chat.get('parse_error'))}</span>")
    gt = inc.get("ground_truth") or {}
    fields = ", ".join((chat.get("request") or {}).get("fields") or list(CHAT_FIELDS))
    lat_max = max(jev["ms"], chat["ms"]) or 1
    fill = {
        "INC_ID": _e(inc["id"]), "ARCH": _e(inc["archetype"]), "STATE": _e(inc["state"].strip()),
        "DATE": _e(_date(trace.get("measured_at"))), "CORPUS": _e(trace.get("corpus_version", "not recorded")),
        "JEV_MODEL": _e(jev.get("model", "")), "CHAT_MODEL": _e(trace["chat_model"]),
        "CHAT_SERVED": _e(f"{chat.get('provider') or ''} · {chat.get('model') or ''}".strip(" ·")),
        "N_Q": str(len(jev["answers"])), "N_CHAT": str(len(CHAT_FIELDS)), "CHAT_FIELDS": _e(fields),
        "JEV_ROWS": answer_rows(jev["answers"]), "GATE_ROWS": gate_rows(g["checks"]),
        "GATE_OUTCOME": _e(g["outcome"]), "GATE_ACTION": _e(g["action"]), "GATE_WHY": _e(g["rationale"]),
        "LABEL": _e(f"our label for this incident: {gt.get('correct_action', '?')}"
                    f"{', safe to automate' if gt.get('auto_safe') else ', not safe to automate'}") if gt else "",
        "JEV_MS": f"{jev['ms']:.0f}", "CHAT_MS": f"{chat['ms']:.0f}",
        "JEV_W": f"{100 * jev['ms'] / lat_max:.1f}", "CHAT_W": f"{100 * chat['ms'] / lat_max:.1f}",
        "JEV_TOK": f"{jev['input_tokens']:,} in / {jev['output_tokens']} out",
        "CHAT_TOK": f"{chat.get('prompt_tokens') or 0:,} in / {chat.get('completion_tokens') or 0} out",
        "CHAT_COST": f"${chat['cost']:.6f}" if chat.get("cost") is not None else "not reported",
        "BILLING": _e(billing), "CHAT_RAW": _e(chat.get("content", "")), "CHAT_PARSE": chat_parse,
        "AGREE_ROWS": rows, "AGREE_TEXT": _e(agree_text),
        "OR_P50": f"{orb.get('p50_ms', 0):.0f}", "OR_P95": f"{orb.get('p95_ms', 0):.0f}",
        "N": str(facts["n"]), "HUB_HREF": href(HUB, ONE_INCIDENT_DIR),
    }
    page = TEMPLATE
    for k, v in fill.items():
        page = page.replace("{{" + k + "}}", v)
    return page


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true",
                    help="re-record the trace with one Jev call and one chat call (paid, < $0.001)")
    ap.add_argument("--incident", default=None, help="incident id (default INC-0001; with --live only)")
    ap.add_argument("--chat-model", default=os.getenv("RACE_MODEL", "openai/gpt-4o-mini"))
    args = ap.parse_args()

    ids = [i.id for i in generate_corpus(n_variants=4)]
    if args.incident and args.incident not in ids:
        ap.error(f"unknown incident {args.incident!r}; the corpus has {ids[0]} to {ids[-1]}")
    if args.live:
        rc = record(args.incident or "INC-0001", args.chat_model)
        if rc:
            return rc
    if not TRACE.exists():
        ap.error(f"{TRACE} does not exist; record one with --live")
    trace = json.loads(TRACE.read_text())
    if args.incident and args.incident != trace["incident"]["id"]:
        ap.error(f"{TRACE.name} holds {trace['incident']['id']}, not {args.incident}; "
                 f"record that incident with --live --incident {args.incident}")
    if "gate" not in trace.get("jev", {}) or "answers" not in trace.get("jev", {}):
        ap.error(f"{TRACE.name} predates the current trace format; re-record it with --live")
    page = build_page(trace)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    print(f"wrote {rel(OUT)} ({len(page) / 1024:.0f} KB) from {TRACE.name} "
          f"({trace['incident']['id']}, recorded {trace.get('measured_at')})")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Two Kinds of Output</title>
<style>
  :root{--navy:#0a2540;--teal:#00838a;--red:#c83737;--green:#1b8a60;--amber:#b86a00;--gray:#5b6472;--line:#e2e6ea;--ink:#111827;--bg:#f7f9fb}
  *{box-sizing:border-box}
  body{margin:0;font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;color:var(--ink);background:var(--bg)}
  header{padding:18px 28px;background:var(--navy);color:#fff}
  header h1{margin:0;font-size:22px}
  header .back{display:inline-block;font-size:12.5px;color:#9ee6e6;text-decoration:none;margin-bottom:6px}
  header .back:hover,header .back:focus-visible{text-decoration:underline}
  header .sub{color:#d3dde8;font-size:14px;margin-top:6px;max-width:900px;line-height:1.5}
  .meta{padding:10px 28px;background:#fff;border-bottom:1px solid var(--line);font-size:13px;color:#334155}
  .wrap{padding:18px 28px;max-width:1400px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:18px;min-width:0;overflow-x:auto}
  h2{margin:0 0 4px;font-size:16px;color:var(--navy)}
  h3{margin:14px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--gray)}
  .kind{font-size:13px;color:#334155;margin-bottom:8px;line-height:1.45}
  table{width:100%;border-collapse:collapse;font-size:13px}
  td,th{padding:5px 6px;border-bottom:1px solid #eef1f4;text-align:left;vertical-align:top}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--gray);font-weight:600}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .t{color:var(--gray);font-size:12px}
  .pass{color:var(--green);font-weight:700}.fail{color:var(--red);font-weight:700}
  .close{display:inline-block;margin-left:4px;padding:0 6px;border-radius:999px;background:#fff4e0;color:var(--amber);font-size:11px;font-weight:700}
  pre{margin:6px 0 0;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;white-space:pre-wrap;background:#0f172a;color:#d7e3f4;border-radius:10px;padding:12px;overflow:auto}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:13px;margin-top:10px}
  .kv .k{color:var(--gray)}
  .badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:700;color:#fff}
  .badge.ok{background:var(--green)}.badge.no{background:var(--red)}
  .outcome{margin-top:10px;padding:10px 12px;border-radius:10px;background:#eef6f6;border-left:5px solid var(--teal);font-size:13.5px}
  .note{margin-top:10px;padding:10px 12px;border-radius:10px;background:#f4f6f8;border-left:5px solid var(--gray);font-size:13.5px;line-height:1.5}
  .lat{display:grid;grid-template-columns:200px 1fr 70px;gap:8px;align-items:center;font-size:13px;margin:6px 0}
  .lat .b{height:14px;border-radius:4px;background:var(--navy)}
  ul{margin:6px 0 0 18px;padding:0;font-size:13.5px;line-height:1.55}
  footer{font-size:12px;color:var(--gray);padding:0 28px 24px}
  code{font-size:12px}
  @media (max-width:900px){ .grid{grid-template-columns:1fr} header,.meta,.wrap{padding-left:16px;padding-right:16px}
    .lat{grid-template-columns:120px 1fr 60px} .m{display:none} td,th{padding:5px 4px} }
</style></head>
<body>
<header>
  <a class="back" href="{{HUB_HREF}}">&larr; All deliverables</a>
  <h1>One incident, two kinds of output</h1>
  <div class="sub">One recorded call each on the same synthetic incident: Jev with {{N_Q}} typed questions, and a
    general chat model asked for {{N_CHAT}} fields as JSON. The point is what each hands back for a gate in code to check.</div>
</header>
<div class="meta">Recorded {{DATE}} · {{INC_ID}} ({{ARCH}}) · one call each from one workstation (n=1), so the
  timings and costs are illustrative · corpus {{CORPUS}}</div>
<div class="wrap">
  <div class="card">
    <h2>The incident text both models received</h2>
    <pre>{{STATE}}</pre>
  </div>
  <div class="grid">
    <section class="card">
      <h2>Jev via OpenRouter <span class="t">{{JEV_MODEL}}</span></h2>
      <div class="kind">Asked {{N_Q}} typed questions (<code>zeroops/schema.py</code>). Each answer comes back as a
        choice or a score with a probability, or as a yes-probability.</div>
      <table><thead><tr><th>Question</th><th>Type</th><th>Answer</th><th>Prob.</th><th class="m">Meaning</th></tr></thead>
        <tbody>{{JEV_ROWS}}</tbody></table>
      <h3>What the gate in zeroops/policy.py does with it</h3>
      <table><thead><tr><th>Check</th><th>Value</th><th>Result</th><th>Margin</th></tr></thead>
        <tbody>{{GATE_ROWS}}</tbody></table>
      <div class="outcome"><b>{{GATE_OUTCOME}} · {{GATE_ACTION}}.</b> {{GATE_WHY}}. <span class="t">({{LABEL}})</span></div>
      <div class="kv"><span class="k">time</span><span>{{JEV_MS}} ms</span>
        <span class="k">tokens</span><span>{{JEV_TOK}}</span>
        <span class="k">cost</span><span>{{BILLING}}</span></div>
    </section>
    <section class="card">
      <h2>Chat model <span class="t">{{CHAT_MODEL}}</span></h2>
      <div class="kind">Asked for {{N_CHAT}} fields ({{CHAT_FIELDS}}) as a JSON object, with OpenRouter's strict
        JSON-schema mode, temperature 0, not streamed. It saw the same incident and the same question list as context.</div>
      <h3>The reply, as returned</h3>
      <pre>{{CHAT_RAW}}</pre>
      <div style="margin-top:8px">{{CHAT_PARSE}}</div>
      <div class="note">The reply has a value per field and no probability. A gate that wants to act only
        when the model is sure would need another signal: a score the model reports about itself, token
        log-probabilities (not requested here), or a second call.</div>
      <div class="kv"><span class="k">time</span><span>{{CHAT_MS}} ms</span>
        <span class="k">tokens</span><span>{{CHAT_TOK}}</span>
        <span class="k">cost</span><span>{{CHAT_COST}} (billed by OpenRouter)</span>
        <span class="k">served by</span><span>{{CHAT_SERVED}}</span></div>
    </section>
  </div>
  <div class="card">
    <h2>Did they give the same answers?</h2>
    <div class="kind">{{AGREE_TEXT}} Jev's real_incident and severity are probabilities and scores; they are
      rounded here to compare with the chat model's yes/no and integer.</div>
    <table><thead><tr><th>Field</th><th>Jev</th><th>Chat model</th><th></th></tr></thead><tbody>{{AGREE_ROWS}}</tbody></table>
  </div>
  <div class="card">
    <h2>Recorded time per call</h2>
    <div class="lat"><span>Jev via OpenRouter</span><span class="b" style="width:{{JEV_W}}%"></span><span>{{JEV_MS}} ms</span></div>
    <div class="lat"><span>{{CHAT_MODEL}}</span><span class="b" style="width:{{CHAT_W}}%;background:var(--gray)"></span><span>{{CHAT_MS}} ms</span></div>
    <div class="kind" style="margin-top:8px">Wall-clock time of one request each, measured from the client. Across the
      {{N}}-incident evaluation run, Jev via OpenRouter took {{OR_P50}} ms at the median and {{OR_P95}} ms at p95.
      The chat model was timed once.</div>
  </div>
  <div class="card">
    <h2>What this comparison can't show</h2>
    <ul>
      <li>Which model is more accurate or faster in general. This is one incident and one call each.</li>
      <li>A like-for-like workload. The chat model answered {{N_CHAT}} fields and Jev {{N_Q}}, so token counts and times
        measure different jobs.</li>
      <li>How often a chat reply fails to parse. Strict JSON-schema mode makes that rare.</li>
      <li>That Jev's reply needs no handling. It is JSON as well, parsed by <code>zeroops/schema.py</code>; a missing or
        malformed answer now sends the incident to a person.</li>
      <li>Whether Jev's probabilities can be trusted as stated. On our {{N}} incidents that is mixed; see the calibration
        chart in the Threshold Lab.</li>
    </ul>
  </div>
</div>
<footer>Our measurement. Trace: <code>work/results/race_trace.json</code>. Page built by <code>scripts/build_race.py</code>
  from that trace with no network calls; <code>--live</code> re-records it.</footer>
</body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
