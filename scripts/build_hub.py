#!/usr/bin/env python3
"""Build the hub (outputs/index.html), the deliverables index (outputs/README.md) and
the Results block in README.md.

Nothing that can change between runs is typed in:
- headline numbers come from work/results/facts.json (written only by scripts/report.py);
- the deck's slide count is read from the .pptx with python-pptx;
- video lengths and resolution come from ffprobe on the .mp4 files;
- the race card reads work/results/race_trace.json.
A deliverable older than the newest decision log is flagged on the hub and in the index as made
from an earlier run, and a missing one is shown as "not built yet". File names come from
zeroops/paths.py.

It also copies the research files the hub links to into outputs/docs/, so outputs/ can
be opened or served on its own. Never serve the project root: it holds .env with live API keys.

The README block between <!-- results:start --> and <!-- results:end --> is replaced on every
run; the rest of README.md is hand-written and left alone.

  ./jev/bin/python scripts/build_hub.py
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops import paths  # noqa: E402
from zeroops.paths import (DASHBOARD_PAGE, DECK_V4, DECK_V4_PDF, DELIVERABLES, LAB_PAGE,  # noqa: E402
                           ONE_INCIDENT_PAGE, QUESTIONS, REPORT, VIDEO_DEMO, href, rel)
from zeroops.schema import incident_questions  # noqa: E402

ROOT = paths.ROOT
RESULTS = paths.RESULTS
OUT = paths.HUB
INDEX_MD = paths.DELIVERABLES_README
README = paths.README
START, END = "<!-- results:start -->", "<!-- results:end -->"

# Research files the hub links to, copied into outputs/docs/ so the folder works on its own.
# copy -> original
DOCS = {paths.research_doc_copy(name): paths.RESEARCH / name for name in paths.RESEARCH_DOCS}
# Frames in outputs/previews/video/, by file-name prefix -> the video they were taken from.
PREVIEW_VIDEO_SOURCES = {"demo_": VIDEO_DEMO}

# Banned in addition to inputs/claims.json (owner's list, phase 2).
EXTRA_BANNED = ["decisions, not strings", "routine third", "decision seam", "rip-and-replace",
                "platform of record", "more autonomy and more safety"]


# ---------------------------------------------------------------- small formatting helpers

def pct(k: int, n: int) -> str:
    return f"{round(100 * k / n)}%" if n else "n/a"


def p2(x: float) -> str:
    return f"{x:.2f}"


def and_list(items: list[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def fmt_duration(seconds: float) -> str:
    """Duration as a player shows it (m:ss, rounded down)."""
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def fmt_date(ts: float) -> str:
    d = datetime.fromtimestamp(ts)
    return f"{d.day} {d:%b %Y}"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- inputs read at build time

def load_facts() -> dict:
    return json.loads(paths.FACTS.read_text())


def newest_decision_log() -> float:
    """mtime of the newest work/results/decisions_*.jsonl (0 if none)."""
    return max((p.stat().st_mtime for p in RESULTS.glob(paths.DECISIONS_GLOB)), default=0.0)


def is_stale(path: Path, reference: float) -> bool:
    return path.exists() and reference > 0 and path.stat().st_mtime < reference


def deck_info(path: Path) -> dict | None:
    """Slide counts from the .pptx: total, the main/appendix split (when a slide is marked
    "Appendix"), and how many slides carry speaker notes. None if missing or unreadable."""
    if not path.exists():
        return None
    try:
        from pptx import Presentation
        slides = list(Presentation(str(path)).slides)
    except Exception as e:  # unreadable or half-written file: say so on the page
        print(f"[warn] could not read {path.name}: {e}")
        return None

    def texts(s) -> list[str]:
        return [sh.text_frame.text.strip() for sh in s.shapes
                if sh.has_text_frame and sh.text_frame.text.strip()]

    total = len(slides)
    notes = sum(1 for s in slides
                if s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip())
    # The first slide with a text box reading just "Appendix" starts the appendix. If it has no
    # slide code such as "A1", it is a divider and counts in neither part.
    first = next((i for i, s in enumerate(slides)
                  if any(x.lower() == "appendix" for x in texts(s))), None)
    if first is None:
        return {"total": total, "main": None, "appendix": None, "notes": notes}
    divider = not any(re.fullmatch(r"A\d+", x) for x in texts(slides[first]))
    return {"total": total, "main": first,
            "appendix": total - first - (1 if divider else 0), "notes": notes}


def video_info(path: Path) -> dict | None:
    """Duration (s) and frame height from ffprobe; None if the file or ffprobe is missing."""
    if not path.exists():
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True).stdout
        data = json.loads(out)
        dur = float(data["format"]["duration"])
        streams = data.get("streams") or [{}]
        return {"duration": dur, "height": streams[0].get("height")}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as e:
        print(f"[warn] ffprobe failed on {path.name}: {e}")
        return {"duration": None, "height": None}


def race_info(path: Path) -> dict | None:
    if not path.exists():
        return None
    t = json.loads(path.read_text())
    jev, chat = t.get("jev") or {}, t.get("chat") or {}
    ja, cp = jev.get("answers") or {}, chat.get("parsed") or {}
    pairs = {"category": ("failure_category", "failure_category"),
             "root cause": ("root_cause", "root_cause"),
             "first action": ("proposed_action", "action")}
    same, differ = [], []

    def value(a):  # raw typed answer ({"type": "choice", "choice": ...}) or a plain value
        return a.get("choice", a) if isinstance(a, dict) else a

    for label, (jk, ck) in pairs.items():
        if jk in ja and ck in cp:
            (same if value(ja[jk]) == cp[ck] else differ).append(label)
    return {"incident": (t.get("incident") or {}).get("id", "one incident"),
            "chat_model": t.get("chat_model") or chat.get("model") or "a chat model",
            "ok": bool(jev.get("ok")) and bool(chat.get("ok")),
            "chat_fields": len(cp), "same": same, "differ": differ,
            "measured_at": t.get("measured_at"), "corpus_version": t.get("corpus_version")}


def dashboard_info() -> tuple[str, int]:
    """(incident the dashboard opens on, number of backends) from work/results/demo_data.json."""
    p = paths.DEMO_DATA
    if not p.exists():
        return "one incident", 0
    groups = json.loads(p.read_text()).get("examples") or []
    first = ((groups[0].get("examples") or [{}]) if groups else [{}])[0]
    return first.get("id", "one incident"), len(groups)


def banned_phrases() -> list[str]:
    try:
        claims = json.loads(paths.CLAIMS.read_text())
        listed = claims.get("banned_phrases") or []
    except (OSError, ValueError):
        listed = []
    return sorted({p.lower() for p in [*listed, *EXTRA_BANNED] if p})


def check_banned(text: str, where: str) -> None:
    """Fail the build if a banned phrase appears as a whole phrase ("unsafe to automate" does
    not match "safe to automate")."""
    low = text.lower()
    hits = [p for p in banned_phrases() if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", low)]
    if hits:
        raise SystemExit(f"banned phrase(s) in {where}: {hits}")


# ---------------------------------------------------------------- copy (plain text, used twice)

def headline(f: dict) -> list[str]:
    """Three headline findings for the primary backend, each with its n and caveat."""
    n, b, j = f["n"], f["backends"]["jev_native"], f["jev"]
    ex, ok = b["action_exact"], b["action_acceptable"]
    out = [
        f"{b['label']} proposed the same first action as our label on {ex['k']} of {n} synthetic "
        f"incidents ({pct(ex['k'], n)}). A looser score that also accepts alternatives we listed "
        f"after the first run gives {ok['k']} of {n} ({pct(ok['k'], n)})."
    ]
    auto, ua, nu = b["auto"], b["unsafe_auto"], f["n_unsafe"]
    if ua == 0:
        s = (f"The gate let it act alone on {auto} of {n}, none of them among the {nu} incidents we "
             f"labelled unsafe to automate. Those {nu} come from only {b['unsafe_templates']} "
             f"scenario types, so the 95% upper bound on the unsafe rate is still "
             f"{round(b['unsafe_templates_upper95_pct'])}%.")
    else:
        s = (f"The gate let it act alone on {auto} of {n}, including {ua} of the {nu} incidents "
             f"we labelled unsafe to automate.")
    if b["missed_incidents"]:
        s += f" It logged {b['missed_incidents']} real incident(s) as noise."
    out.append(s)
    near = j["autos_near_page_cutoff"]
    t = (f"Most of those calls were close: {near['k']} of the {near['of']} passed the "
         f"\"page a human?\" check with a probability between {p2(near['min'])} and "
         f"{p2(near['max'])}, against a cut-off of {p2(near['cutoff'])}.")
    lower = sorted((s for s in j.get("sensitivity", [])
                    if "page_min" in s["thresholds"] and s["thresholds"]["page_min"] < near["cutoff"]),
                   key=lambda s: s["thresholds"]["page_min"])
    if lower:
        first, rest = lower[0], lower[1:]
        t += (f" With the cut-off at {p2(first['thresholds']['page_min'])} it would have acted "
              f"alone on {first['auto']}")
        t += "".join(f", at {p2(s['thresholds']['page_min'])} on {s['auto']}" for s in rest) + "."
    out.append(t)
    return out


def caveats(f: dict) -> list[str]:
    n, b, j = f["n"], f["backends"]["jev_native"], f["jev"]
    t = f["n_templates"]
    c, e, dc = j["category_conf_ge_0_9"], j["endpoints"], j["data_corruption"]
    lo, hi = dc["severity_range"]
    parts = [f"the {k} ({v})" for k, v in dc["stopped_by"].items()]
    stopped = and_list(parts)
    nps = j["needs_page_mean"]
    return [
        f"The incidents come from {t} hand-written templates, each reused {n // t} times with "
        f"different service names and numbers, so the evidence is closer to {t} cases than to {n}. "
        f"Root cause scored {pct(b['root_cause']['k'], n)} because the clues are explicit.",
        f"The acceptable-action list was written after the first run was scored. "
        f"{j['lenient_only_incidents']} incidents in {len(j['lenient_only_templates'])} templates "
        f"get credit only through it.",
        f"Jev proposed {j['first_listed_action']}, the first option in the list, "
        f"{j['first_option_proposed']} times; our labels call for it {j['first_option_labelled']} "
        f"times. Options were never shuffled, so this may be order bias.",
        f"On all {dc['n']} data-corruption incidents (labelled SEV1) Jev proposed a rollback and "
        f"rated severity {p2(lo)}-{p2(hi)} on a 0-3 scale where our label was "
        f"{dc['labelled_severity']}. The gate escalated them, stopped by {stopped}.",
        f"Category answers given with 0.9 or more confidence were right {c['correct']} of "
        f"{c['n']} times at a mean stated confidence of {p2(c['mean_conf'])}. The \"page a human?\" "
        f"probability averaged {p2(nps['safe_real'])} on real incidents we labelled safe and "
        f"{p2(nps['unsafe'])} on those labelled unsafe, so on its own it does not separate them.",
        f"The same model version through TypeSafe's API and through OpenRouter gave different "
        f"probabilities on {e['prob_differs']} of {e['n']} incidents and a different gate outcome "
        f"on {len(e['outcome_differs'])} ({', '.join(e['outcome_differs'])}).",
        "Latency was measured once, from one workstation. " + cost_note(b),
    ]


def cost_note(b: dict) -> str:
    if b.get("cost_basis", "").startswith("estimated"):
        return (f"{b['label']} returns no cost, so its figure is an estimate: OpenRouter's billed "
                f"per-token rate applied to its mean of {b['mean_input_tokens']:,.0f} input tokens a call.")
    return f"Cost basis for {b['label']}: {b.get('cost_basis', 'not recorded')}."


def cost_cell(b: dict) -> str:
    if not b["cost_per_1k_usd"]:
        return "no API fee (GPU not costed)"
    basis = b.get("cost_basis", "")
    tag = ", estimated" if basis.startswith("estimated") else ", billed" if basis.startswith("billed") else ""
    return f"${b['cost_per_1k_usd']:.3f}{tag}"


def readme_block(f: dict) -> str:
    n = f["n"]
    rows = []
    for b in f["backends"].values():
        ex, ok = b["action_exact"], b["action_acceptable"]
        unsafe = f"{b['unsafe_auto']} of {b['unsafe_cases']}" + (" (never acted)" if b["auto"] == 0 else "")
        rows.append(
            f"| {b['label']} | `{b['model']}` | {ex['k']}/{n} ({pct(ex['k'], n)}) | "
            f"{ok['k']}/{n} ({pct(ok['k'], n)}) | {b['auto']} | {unsafe} | {b['missed_incidents']} | "
            f"{round(b['p50_ms'])} / {round(b['p95_ms'])} ms | {cost_cell(b)} |")
    lines = [
        START,
        "<!-- Generated by scripts/build_hub.py from work/results/facts.json; hand edits here are overwritten. -->",
        f"*Our measurement*, {n} synthetic incidents, corpus version `{f['corpus_version']}`.",
        "",
        *[f"- {s}" for s in headline(f)],
        "",
        "| Backend | Model | Exact action | Acceptable action | Acted alone | Unsafe cases automated "
        "| Real incidents missed | Median / p95 latency | API cost per 1,000 |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "Before quoting any of this:",
        *[f"- {s}" for s in caveats(f)],
        "",
        "Full tables, column definitions and the calibration buckets: "
        f"[`{rel(REPORT)}`]({rel(REPORT)}).",
        END,
    ]
    return "\n".join(lines)


def update_readme(f: dict) -> bool:
    text = README.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"README.md has no {START} ... {END} block; add the markers first")
    block = readme_block(f)
    check_banned(block, "README results block")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = head + block + tail
    if new != text:
        README.write_text(new)
        return True
    return False


# ---------------------------------------------------------------- page

CSS = """
  :root{--teal:#00a3a3;--accent:#5eead4;--ink:#eaf1fb;--muted:#9fb0c9;--line:#1e2b45;
        --panel:rgba(15,23,42,.72);--warn:#fbbf24;color-scheme:dark}
  *{box-sizing:border-box}
  body{margin:0;font-family:Inter,system-ui,"Segoe UI",Arial,sans-serif;color:var(--ink);
       background-color:#0a0f1a;
       background-image:radial-gradient(1000px 500px at 15% -10%,#16223c 0%,#0a0f1a 55%);
       background-repeat:no-repeat}
  .wrap{max-width:1080px;margin:0 auto;padding:56px 24px 80px}
  h1{color:#fff;font-size:clamp(24px,6vw,34px);line-height:1.2;margin:0 0 8px}
  h1 .a{color:var(--accent)}
  .sub{color:var(--muted);font-size:15px;line-height:1.55;margin:0 0 28px;max-width:760px}
  h2.section{color:#c9d6e2;font-size:13px;letter-spacing:.08em;text-transform:uppercase;margin:34px 0 12px}
  .measured{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
  .measured .label{font-size:11px;color:var(--accent);letter-spacing:.06em;text-transform:uppercase}
  .measured ul{margin:10px 0 0;padding-left:20px}
  .measured li{font-size:14px;line-height:1.55;color:#d5deea;margin-bottom:8px}
  .measured p{font-size:13px;line-height:1.55;color:var(--muted);margin:10px 0 0}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:16px}
  .card{display:block;text-decoration:none;color:inherit;background:var(--panel);
        border:1px solid var(--line);border-radius:16px;padding:18px 20px;
        transition:border-color .15s,transform .15s}
  a.card:hover,a.card:focus-visible{border-color:var(--teal);transform:translateY(-2px);outline:none}
  .card h3{margin:0 0 6px;font-size:17px;color:var(--ink)}
  .card p{margin:0;font-size:13px;color:var(--muted);line-height:1.5}
  .card.missing{opacity:.6;border-style:dashed}
  .card .warn{margin-top:8px;font-size:12px;color:var(--warn);line-height:1.45;font-variant-ligatures:none}
  .tags{margin-top:10px;font-size:11px;color:var(--accent);letter-spacing:.06em;text-transform:uppercase}
  footer{color:#7b8aa3;font-size:12px;margin-top:40px;line-height:1.7}
  footer p{margin:0 0 8px}
  a{color:var(--accent)}
  code{background:#0f172a;border:1px solid var(--line);border-radius:6px;padding:1px 6px;
       color:#c9d6e2;overflow-wrap:anywhere}
  @media (max-width:600px){.wrap{padding:32px 16px 56px}.sub{font-size:14px}}
"""


def card(href: str, title: str, desc: str, tags: list[str], *, exists: bool = True,
         warn: str | None = None, build_hint: str | None = None) -> str:
    tag_html = f'<div class="tags">{esc(" · ".join(t for t in tags if t))}</div>'
    if not exists:
        hint = f' Not built yet: run <code>{esc(build_hint)}</code>.' if build_hint else " Not built yet."
        return (f'<div class="card missing"><h3>{esc(title)}</h3><p>{esc(desc)}{hint}</p>'
                f'{tag_html}</div>')
    warn_html = f'<div class="warn">{esc(warn)}</div>' if warn else ""
    return (f'<a class="card" href="{esc(href)}"><h3>{esc(title)}</h3><p>{esc(desc)}</p>'
            f'{warn_html}{tag_html}</a>')


def stale_note(path: Path, ref: float, fix: str) -> str | None:
    """Warning for a deliverable older than the newest decision log; `fix` is a full sentence."""
    if is_stale(path, ref):
        return (f"Made before the current decision logs ({fmt_date(ref)}), so its numbers and wording "
                f"may be out of date. {fix}")
    return None


def video_tags(info: dict | None) -> list[str]:
    if not info:
        return ["MP4"]
    h = info.get("height")
    return ["MP4", f"{h}p" if h else "", fmt_duration(info["duration"]) if info.get("duration") else ""]


def race_copy(race: dict | None, f: dict, nq: int) -> tuple[str, list[str], str | None]:
    """Description, tags and warning for the race card, from work/results/race_trace.json."""
    if not race:
        return "One recorded call each to Jev and to a chat model on the same incident.", ["HTML"], None
    if race["ok"] and race["same"] and not race["differ"]:
        agree = f"Both gave the same {and_list(race['same'])}."
    elif race["differ"]:
        agree = f"They differed on {and_list(race['differ'])}."
    else:
        agree = "One of the two calls failed; the page shows what came back."
    desc = (f"One recorded call each to Jev ({nq} typed questions) and to {race['chat_model']} "
            f"({race['chat_fields']} JSON fields) on {race['incident']}. {agree} The page shows what "
            f"each hands back for a gate to check: Jev attaches a probability to each answer, the "
            f"chat reply carries values only. One pair of calls, so the timings are illustrative.")
    recorded = ""
    if race.get("measured_at"):
        try:
            recorded = f"recorded {fmt_date(datetime.fromisoformat(race['measured_at']).timestamp())}"
        except ValueError:
            recorded = f"recorded {race['measured_at']}"
    warn = None
    if not race.get("corpus_version"):
        warn = "The trace doesn't say which corpus version it was recorded on."
    elif race["corpus_version"] != f["corpus_version"]:
        warn = ("Recorded on an earlier version of the incident corpus. "
                "Re-record with scripts/build_race.py --live (paid).")
    return desc, ["HTML", "replay of recorded calls", recorded], warn


def build_page(f: dict) -> str:
    n, t = f["n"], f["n_templates"]
    nq = len(incident_questions())
    nb = len(f["backends"])
    ref = newest_decision_log()
    run_date = fmt_date(ref) if ref else "unknown date"

    deck_path = DECK_V4
    deck = deck_info(deck_path)
    if deck and deck["main"] is not None:
        deck_size = f"{deck['main']} slides + {deck['appendix']}-slide appendix"
    elif deck:
        deck_size = f"{deck['total']} slides"
    else:
        deck_size = ""
    if deck:
        notes = ("speaker notes on every slide" if deck["notes"] == deck["total"]
                 else f"speaker notes on {deck['notes']} of {deck['total']} slides")
    else:
        notes = ""

    vids = {p: video_info(p) for p in (VIDEO_DEMO,)}
    race = race_info(paths.RACE_TRACE)
    dash_incident, k_backends = dashboard_info()

    def dur_title(base: str, p: Path) -> str:
        v = vids[p]
        return f"{base}, {fmt_duration(v['duration'])}" if v and v.get("duration") else base

    # --- start here
    start = [
        card(href(DECK_V4), "Discussion deck (v4)",
             "Start here. The main document: the industry shift, the gap at the decision step, what a "
             "decision model adds, a network example, the value and the staged path.",
             ["PowerPoint", deck_size or "deck"], exists=DECK_V4.exists(),
             build_hint="./jev/bin/python scripts/build_v4.py"),
        card(href(REPORT), "Results report",
             "Every table behind the summaries: answer quality per backend, what the gate did with "
             "the answers, speed and cost with where each cost figure comes from, and whether "
             "stated confidence tracked accuracy. Column definitions at the end.",
             ["Markdown", "generated by report.py"], exists=REPORT.exists(),
             build_hint="./jev/bin/python scripts/report.py"),
    ]
    start.insert(1, card(
        href(QUESTIONS), "Open questions and next steps",
        "The reference behind the end of the story: what decides whether the opportunity holds "
        "for a given incident estate, the questions IT would need to answer with who owns each "
        "and what evidence settles it, and a staged way to find out on your own tickets.",
        ["Markdown", "generated by build_questions.py"], exists=QUESTIONS.exists(),
        warn=stale_note(QUESTIONS, ref, "Rebuild with scripts/build_questions.py."),
        build_hint="./jev/bin/python scripts/build_questions.py"))

    # --- see it work
    lab = LAB_PAGE
    dash = DASHBOARD_PAGE
    race_page = ONE_INCIDENT_PAGE
    race_desc, race_tags, race_warn = race_copy(race, f, nq)
    see = [
        card(href(lab), "Threshold Lab",
             f"Change the gate's thresholds and see which of the {n} recorded decisions move between "
             f"act, page and log. The model's answers were recorded once and stay fixed; only the "
             f"code's decision changes. Shows exact and acceptable action side by side, real "
             f"incidents logged as noise, and a sweep of the \"page a human?\" cut-off.",
             ["HTML", "interactive", f"{nb} backends"], exists=lab.exists(),
             warn=stale_note(lab, ref, "Rebuild with scripts/build_lab.py."),
             build_hint="./jev/bin/python scripts/build_lab.py"),
        card(href(dash), "Dashboard",
             f"One incident, {dash_incident}, as a dashboard: the alert, the {nq} answers with their "
             f"probabilities, each gate check with its margin, and the outcome. The chips switch "
             f"between the {k_backends} backends' recorded answers. The loop video below is "
             f"rendered from this page.",
             ["HTML", "recorded answers"], exists=dash.exists(),
             warn=stale_note(dash, ref, "Rebuild with scripts/build_demo.py."),
             build_hint="./jev/bin/python scripts/build_demo.py"),
        card(href(race_page), "One incident, two kinds of output", race_desc, race_tags,
             exists=race_page.exists(), warn=race_warn,
             build_hint="./jev/bin/python scripts/build_race.py"),
    ]

    # --- presentations
    pres = [
        card(href(deck_path), "Discussion deck (v4)",
             "For a conversation with a CIO: the industry shift, the gap at the decision step, what a "
             "decision model adds, a network example end to end, the value, the open questions and a "
             "staged path. Figures are read from work/results/facts.json when the deck is built.",
             ["PPTX", deck_size, notes], exists=deck_path.exists(),
             build_hint="./jev/bin/python scripts/build_v4.py"),
        card(href(VIDEO_DEMO), dur_title("Demo video", VIDEO_DEMO),
             "The whole story in a few minutes: how incidents run today, the gap at the decision "
             "step, what a decision model adds, a network example end to end, the value, and the "
             "staged path.",
             video_tags(vids[VIDEO_DEMO]), exists=vids[VIDEO_DEMO] is not None,
             warn=stale_note(VIDEO_DEMO, ref, "Rebuild with scripts/run_all.py --videos."),
             build_hint="./jev/bin/python scripts/run_all.py --skip-api --skip-local --videos"),
    ]

    # --- research
    research = [
        card(href(paths.research_doc_copy("README.md")), "Research index",
             "What each research file is, where it came from and how far to trust it, with the "
             "weak sources we found.", ["Markdown"]),
        card(href(paths.research_doc_copy("landscape-synthesis.md")), "Market landscape",
             "Who sells what in incident decision-making (ITSM, observability, AIOps, agentic SRE, "
             "runbook automation), a component-by-component build/buy table, and the independent "
             "evidence on Jev so far.", ["Markdown", "AI-assisted synthesis"]),
        card(href(paths.research_doc_copy("independent-review-claude.md")), "Review of Jev (Claude)",
             "Jev's maturity, its documented failure modes (prompt injection, option order, no "
             "arithmetic, long inputs), published security tests, ServiceNow integration, and one "
             "way to structure a trial.", ["Markdown", "AI-generated desk research"]),
        card(href(paths.research_doc_copy("build-vs-buy-gemini-openai.txt")), "Build vs buy (Gemini/OpenAI)",
             "What is easy or hard to build yourself, an event contract, layered correlation and a "
             "phased build/buy roadmap. Check sources before quoting.",
             ["Text", "AI-generated desk research"]),
        card(href(paths.research_doc_copy("composable-stack-and-compliance-gemini-openai.txt")),
             "Composable stack and compliance (Gemini/OpenAI)",
             "Event routing, OpenTelemetry layouts, typed models compared with LLMs, injection risk "
             "and the EU AI Act. Parts overstate the case; the research index lists them.",
             ["Text", "AI-generated desk research"]),
    ]

    measured = "".join(f"<li>{esc(s)}</li>" for s in headline(f))
    models = "; ".join(f"{b['label']} <code>{esc(b['model'])}</code>" for b in f["backends"].values())

    def section(title: str, cards: list[str]) -> str:
        return f'<h2 class="section">{esc(title)}</h2>\n<div class="grid">\n' + "\n".join(cards) + "\n</div>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Jev demo hub</title>
<!-- Generated by scripts/build_hub.py; hand edits here are overwritten. -->
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>ZeroOps · <span class="a">Jev</span> in incident triage</h1>
  <p class="sub">AI agents for incident response became a real category in 2026, yet the routine
  judgment calls in incident management (is it real, whose is it, how bad, act or page) still sit
  with hand-written rules and whoever is on call, in application incidents and network monitoring
  alike. This demo shows what a typed decision model, TypeSafe's Jev, can do in those calls: {nq}
  typed questions per incident in one call, answers with probabilities, and the act-or-page gate
  written in ordinary code, run on {n} synthetic incidents. The material ends with the value it
  could have and a staged way to test it on real tickets.</p>

  <div class="measured">
    <div class="label">What the demo measured · Our measurement</div>
    <ul>{measured}</ul>
    <p>The incidents were written and labelled for the demo from {t} templates with explicit clues,
    and there is no held-out set, so they show the mechanism and your own tickets are the real test.
    The <a href="{esc(href(REPORT))}">results report</a> has every table and its definitions.</p>
  </div>

  {section("Start here", start)}
  {section("See it work", see)}
  {section("Presentations", pres)}
  {section("Background research", research)}

  <footer>
    <p>Rebuild these pages from the saved results, with no API calls:
    <code>./jev/bin/python scripts/run_all.py --skip-api --skip-local</code>. Re-running the
    evaluation, re-recording the two-outputs page (<code>--race-live</code>) or remaking the videos
    (<code>--videos</code>) calls paid APIs; README.md lists which step costs what.</p>
    <p>Data: {n} synthetic incidents ({t} templates × {n // t} variants), corpus version
    <code>{esc(f['corpus_version'])}</code>, decision logs written {run_date}. Models: {models}.</p>
    <p>Every file in this folder, in reading order, with sizes and build dates:
    <a href="{esc(href(INDEX_MD))}">{esc(href(INDEX_MD))}</a>. A PDF of the deck for quick viewing:
    <a href="{esc(href(DECK_V4_PDF))}">{esc(href(DECK_V4_PDF))}</a>; slide images, video frames and page
    screenshots: <a href="{esc(href(paths.PREVIEWS))}/">{esc(href(paths.PREVIEWS))}/</a>.</p>
    <p>This folder works on its own. To serve it, from the project root:
    <code>python3 -m http.server --directory {esc(rel(DELIVERABLES))} --bind 127.0.0.1</code>.
    The files under <code>{esc(href(paths.DOCS))}/</code> are copies made by <code>scripts/build_hub.py</code>; edit the
    originals in <code>{esc(rel(paths.RESEARCH))}/</code>. Don't serve the project root, which
    holds <code>.env</code>.</p>
  </footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------- outputs/README.md

def fmt_bytes(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(1, round(n / 1e3))} KB"


def fmt_built(ts: float) -> str:
    d = datetime.fromtimestamp(ts)
    return f"{d.day} {d:%b %Y} {d:%H:%M}"


def pdf_pages(path: Path) -> int | None:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30,
                             check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else None


def word_count(path: Path) -> str:
    return f"{len(path.read_text().split()):,} words"


def files_in(folder: Path, pattern: str = "*") -> list[Path]:
    return sorted(p for p in folder.rglob(pattern) if p.is_file()) if folder.is_dir() else []


def older_than(files: list[Path], refs: list[tuple[str, float]]) -> str | None:
    """The first reference (label, mtime) that some file predates, as a short reason."""
    for label, ts in refs:
        if ts and any(p.stat().st_mtime < ts for p in files):
            return f"older than {label}"
    return None


def index_row(path: Path, what: str, how: str, size: str, refs: list[tuple[str, float]],
              link: Path | None = None, build: str = "", files: list[Path] | None = None,
              warn: str | None = None) -> str:
    name = href(path) + ("/" if path.is_dir() else "")
    cell = f"[{name}]({href(link or path)})"
    files = files if files is not None else ([path] if path.is_file() else [])
    if not path.exists() or not files:
        return f"| {cell} | {what} | {how} | not built yet | | run `{build}` |" if build else \
            f"| {cell} | {what} | {how} | not built yet | | |"
    built = fmt_built(max(p.stat().st_mtime for p in files))
    why = warn or older_than(files, refs)
    fresh = f"may be out of date: {why}" if why else "yes"
    return f"| {cell} | {what} | {how} | {size} | {built} | {fresh} |"


def deliverables_index(f: dict) -> str:
    """outputs/README.md: every file in reading order, what it is, how to open it, its size
    or length, when it was built and whether it may be out of date."""
    ref = newest_decision_log()
    logs = [(f"the decision logs ({fmt_date(ref)})", ref)] if ref else []
    deck_ts = DECK_V4.stat().st_mtime if DECK_V4.exists() else 0.0
    deck = deck_info(DECK_V4)
    if deck and deck["main"] is not None:
        deck_size = f"{deck['total']} slides ({deck['main']} + {deck['appendix']}-slide appendix)"
    else:
        deck_size = f"{deck['total']} slides" if deck else ""

    def size_of(p: Path) -> int:
        return p.stat().st_size if p.exists() else 0

    def video(p: Path) -> str:
        v = video_info(p) or {}
        bits = [fmt_duration(v["duration"]) if v.get("duration") else "",
                f"{v['height']}p" if v.get("height") else "", fmt_bytes(size_of(p))]
        return ", ".join(b for b in bits if b)

    pages = pdf_pages(DECK_V4_PDF) if DECK_V4_PDF.exists() else None
    md = "Markdown: any text editor or Markdown preview"
    player = "any video player, or the hub"
    browser = "a browser (from the hub, or open the file)"
    videos = "./jev/bin/python scripts/run_all.py --skip-api --skip-local --videos"

    numbered = [
        index_row(DECK_V4, "Discussion deck (v4) with speaker notes, for a conversation with a CIO",
                  "PowerPoint, Keynote or LibreOffice Impress",
                  ", ".join(x for x in (deck_size, fmt_bytes(size_of(DECK_V4))) if x), logs,
                  build="./jev/bin/python scripts/build_v4.py"),
        index_row(DECK_V4_PDF, "The deck as a PDF, for quick viewing; no speaker notes",
                  "any PDF viewer",
                  ", ".join(x for x in (f"{pages} pages" if pages else "", fmt_bytes(size_of(DECK_V4_PDF))) if x),
                  [("the deck", deck_ts), *logs], build="./jev/bin/python scripts/build_v4.py"),
        index_row(QUESTIONS, "Open questions and next steps: considerations, the questions by owner, "
                  "and a staged way to find out on your own tickets", md,
                  word_count(QUESTIONS) if QUESTIONS.exists() else "", logs,
                  build="./jev/bin/python scripts/build_questions.py"),
        index_row(VIDEO_DEMO, "Demo video, narrated: the whole story in a few minutes", player,
                  video(VIDEO_DEMO), logs, build=videos),
        index_row(REPORT, "Results report: every table behind the summaries, with column definitions", md,
                  word_count(REPORT) if REPORT.exists() else "", logs,
                  build="./jev/bin/python scripts/report.py"),
    ]

    race = race_info(paths.RACE_TRACE)
    _, _, race_warn = race_copy(race, f, len(incident_questions()))
    deck_imgs = files_in(paths.PREVIEWS_DECK, f"{paths.DECK_PREVIEW_PREFIX}-*.png")
    frames = files_in(paths.PREVIEWS_VIDEO, "*.png")
    shots = files_in(paths.PREVIEWS_PAGES, "*.png")
    stale_frames = [p for p in frames for prefix, vid in PREVIEW_VIDEO_SOURCES.items()
                    if p.name.startswith(prefix) and vid.exists() and p.stat().st_mtime < vid.stat().st_mtime]
    stale_shots = [p for p, page in ((paths.PREVIEW_LAB, LAB_PAGE),
                                     (paths.PREVIEW_ONE_INCIDENT, ONE_INCIDENT_PAGE))
                   if p.exists() and page.exists() and p.stat().st_mtime < page.stat().st_mtime]
    docs = files_in(paths.DOCS)
    others = [
        index_row(OUT, "Hub page: everything below, with descriptions and the headline results", browser,
                  fmt_bytes(size_of(OUT)), []),
        index_row(paths.LAB_DIR, "Threshold Lab: move the gate's thresholds and see which recorded "
                  "decisions change", browser, fmt_bytes(size_of(LAB_PAGE)), logs, link=LAB_PAGE,
                  build="./jev/bin/python scripts/build_lab.py", files=[LAB_PAGE] if LAB_PAGE.exists() else []),
        index_row(paths.ONE_INCIDENT_DIR, "One incident, two kinds of output: one recorded call each to Jev "
                  "and to a chat model", browser, fmt_bytes(size_of(ONE_INCIDENT_PAGE)), [],
                  link=ONE_INCIDENT_PAGE, build="./jev/bin/python scripts/build_race.py",
                  files=[ONE_INCIDENT_PAGE] if ONE_INCIDENT_PAGE.exists() else [], warn=race_warn),
        index_row(paths.DASHBOARD_DIR, "Dashboard: one incident, its answers, each gate check and the "
                  f"outcome; the loop video (6) is rendered from this page ({rel(paths.LOOP_PAGE)})",
                  browser, fmt_bytes(size_of(DASHBOARD_PAGE)), logs, link=DASHBOARD_PAGE,
                  build="./jev/bin/python scripts/build_demo.py",
                  files=[DASHBOARD_PAGE] if DASHBOARD_PAGE.exists() else []),
        index_row(paths.PREVIEWS_DECK, "Slide images of the deck, one PNG per slide (50 dpi)",
                  "any image viewer", f"{len(deck_imgs)} images", [("the deck", deck_ts)],
                  link=deck_imgs[0] if deck_imgs else paths.PREVIEWS_DECK, files=deck_imgs,
                  build="./jev/bin/python scripts/build_v4.py"),
        index_row(paths.PREVIEWS_VIDEO, "Still frames from the demo video", "any image viewer",
                  f"{len(frames)} images", [],
                  link=paths.PREVIEWS_VIDEO, files=frames,
                  warn=f"{len(stale_frames)} frame(s) older than their video" if stale_frames else None),
        index_row(paths.PREVIEWS_PAGES, "Screenshots of the Threshold Lab and the one-incident page",
                  "any image viewer", f"{len(shots)} images", [], link=paths.PREVIEWS_PAGES, files=shots,
                  warn=(f"{and_list([p.name for p in stale_shots])} older than the page"
                        if stale_shots else None)),
        index_row(paths.DOCS, f"Copies of the research files the hub links to (originals in "
                  f"`{rel(paths.RESEARCH)}/`, copied by build_hub.py)", md, f"{len(docs)} files", [],
                  link=paths.research_doc_copy("README.md"), files=docs),
    ]
    head = "| File | What it is | How to open | Size or length | Built | Up to date? |\n|---|---|---|---|---|---|"
    serve = f"python3 -m http.server 8000 --directory {rel(DELIVERABLES)} --bind 127.0.0.1"
    return "\n".join([
        "# Deliverables",
        "",
        "<!-- Generated by scripts/build_hub.py; hand edits here are overwritten. -->",
        "",
        "Everything to open, read or present, numbered in reading order. "
        f"[`{href(OUT)}`]({href(OUT)}) is the hub page: the same files with descriptions. Open it in a "
        f"browser, or serve this folder on its own from the project root with `{serve}`. "
        "Never serve the project root: it holds `.env`.",
        "",
        f"\"Up to date?\" compares each file with the newest decision log in `{rel(RESULTS)}/`"
        f"{f' (written {fmt_date(ref)})' if ref else ''} and with the file it was made from. "
        "\"May be out of date\" means the file is older, so its numbers or wording may lag; "
        "the last column names the builder to re-run when a file is missing.",
        "",
        "## In reading order",
        "",
        head,
        *numbered,
        "",
        "## Pages and folders",
        "",
        head,
        *others,
        "",
        f"Sources and raw data live outside this folder: storyline and the questions template in "
        f"`{rel(paths.CONTENT)}/`, raw run data in `{rel(RESULTS)}/` (decision logs, `{paths.FACTS.name}`, "
        f"`{paths.METRICS.name}`), HyperFrames video sources in `{rel(paths.VIDEO_SRC)}/`, research "
        f"originals in `{rel(paths.RESEARCH)}/`, builders in `{rel(paths.SCRIPTS)}/`. Rebuild everything "
        "here with no API calls: `./jev/bin/python scripts/run_all.py --skip-api --skip-local`.",
        "",
    ])


def copy_docs() -> list[str]:
    """Mirror the linked documents into outputs/docs/ and drop files no longer linked."""
    written = []
    for d, s in DOCS.items():
        if not s.exists():
            print(f"[warn] {rel(s)} missing; {rel(d)} not copied")
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(s, d)
        written.append(rel(d))
    docs_root = paths.DOCS
    keep = set(DOCS)
    for p in sorted(docs_root.rglob("*"), reverse=True):
        if p.is_file() and p not in keep:
            p.unlink()
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    return written


def main() -> int:
    facts = load_facts()
    page = build_page(facts)
    check_banned(page, rel(OUT))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    docs = copy_docs()
    index = deliverables_index(facts)
    check_banned(index, rel(INDEX_MD))
    INDEX_MD.write_text(index)
    changed = update_readme(facts)
    print(f"wrote {rel(OUT)} and {rel(INDEX_MD)}; copied {len(docs)} docs into {rel(paths.DOCS)}/; "
          f"README results block {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
