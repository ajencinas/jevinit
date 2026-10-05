#!/usr/bin/env python3
"""Smoke test: one call to each proprietary Jev path with the real 12-question schema.

Both paths speak the same System One wire format (state + typed questions) and are called
through the same adapters the evaluation uses, with the pinned model versions:

  - Jev native    : POST https://api.typesafe.ai/v1/systemone   (zeroops.adapters.native_adapter)
  - Jev OpenRouter: POST https://openrouter.ai/api/v1/systemone (zeroops.adapters.openrouter_adapter)

Each answer is checked against zeroops.schema.incident_questions(): every question answered,
with the declared type, a value of the right kind (a declared option, a score on the declared
scale, a probability in 0..1) and a confidence where the type has one.

Run:  ./jev/bin/python scripts/smoke_api.py     (two paid calls, about $0.0001 in total)
Reads keys from the project .env (OPENROUTER_API / TYPESAFE_API or *_API_KEY).
Writes work/results/smoke_api.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402

from zeroops.paths import ENV, SMOKE_API, rel  # noqa: E402

load_dotenv(ENV)

from zeroops import adapters  # noqa: E402
from zeroops.corpus import generate_corpus  # noqa: E402
from zeroops.schema import incident_questions  # noqa: E402

console = Console()
INCIDENT_ID = "INC-0001"


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None   # rejects NaN


def validate(answers: Any, questions: dict[str, dict]) -> list[str]:
    """Problems with a System One `answers` payload, checked against the question schema."""
    if not isinstance(answers, dict):
        return [f"answers is {type(answers).__name__}, expected an object"]
    problems = []
    extra = sorted(set(answers) - set(questions))
    if extra:
        problems.append(f"unexpected answers: {', '.join(extra)}")
    for qid, spec in questions.items():
        a = answers.get(qid)
        if not isinstance(a, dict):
            problems.append(f"{qid}: missing")
            continue
        t = spec["type"]
        if a.get("type") not in (None, t):
            problems.append(f"{qid}: type {a.get('type')!r}, expected {t!r}")
        if t == "choice":
            if a.get("choice") not in spec["criteria"]:
                problems.append(f"{qid}: choice {a.get('choice')!r} is not a declared option")
            if _num(a.get("confidence")) is None:
                problems.append(f"{qid}: no numeric confidence")
            if not isinstance(a.get("probabilities"), dict):
                problems.append(f"{qid}: no probabilities")
        elif t == "score":
            s, top = _num(a.get("score")), len(spec["criteria"]) - 1
            if s is None or not 0 <= s <= top:
                problems.append(f"{qid}: score {a.get('score')!r} not on the 0..{top} scale")
            if _num(a.get("confidence")) is None:
                problems.append(f"{qid}: no numeric confidence")
        elif t == "noul":
            v = _num(a.get("noul"))
            if v is None or not 0 <= v <= 1:
                problems.append(f"{qid}: noul {a.get('noul')!r} is not a probability")
    return problems


def check(tag: str, adapter: adapters.HttpSystemOneAdapter, state: str, questions: dict) -> dict:
    console.rule(f"[bold]{tag}: {adapter.endpoint}  model={adapter.model}[/bold]")
    if not adapter.api_key:
        console.print("[red]API key not set; skipping[/red]")
        return {"ok": False, "error": "missing key"}
    res = adapter.decide(state, questions)
    out: dict[str, Any] = {"latency_ms": round(res.latency_ms, 1), "attempts": res.attempts,
                           "model": res.model, "provider": res.provider,
                           "usage": (res.raw or {}).get("usage") if isinstance(res.raw, dict) else None}
    if not res.ok:
        console.print(f"[red]call failed after {res.attempts} attempt(s): {res.error}[/red]")
        return {**out, "ok": False, "error": res.error}
    answers = res.raw.get("answers")
    console.print(Panel(Syntax(json.dumps(res.raw, indent=2, ensure_ascii=False), "json", word_wrap=True),
                        title=f"{tag} response", border_style="cyan"))
    problems = validate(answers, questions)
    if res.parsed.missing:
        problems.append(f"parser marked missing: {', '.join(res.parsed.missing)}")
    if problems:
        console.print("[yellow]" + "\n".join(problems) + "[/yellow]")
    else:
        console.print(f"[green]OK[/green] all {len(questions)} answers well-formed · "
                      f"{res.latency_ms:.0f} ms · usage={out['usage']}")
    return {**out, "ok": not problems, "problems": problems, "answers": answers,
            "parsed": {"real_incident": res.parsed.real_incident,
                       "failure_category": res.parsed.failure_category,
                       "severity": res.parsed.severity,
                       "proposed_action": res.parsed.proposed_action}}


def main() -> int:
    questions = incident_questions()
    inc = next(i for i in generate_corpus(n_variants=4) if i.id == INCIDENT_ID)
    native, orouter = adapters.native_adapter(), adapters.openrouter_adapter()
    console.print(Panel.fit(
        f"Jev API smoke test · {inc.id} ({inc.archetype}) · {len(questions)} typed questions\n"
        f"TYPESAFE_API: {'set' if native.api_key else 'MISSING'}   "
        f"OPENROUTER_API: {'set' if orouter.api_key else 'MISSING'}", border_style="blue"))
    n = check("Jev native", native, inc.state, questions)
    console.print()
    o = check("Jev via OpenRouter", orouter, inc.state, questions)
    console.print()

    if n.get("ok") and o.get("ok"):
        pn, po = n["parsed"], o["parsed"]
        console.print("native vs OpenRouter on the same input: "
                      f"category {pn['failure_category']} / {po['failure_category']}, "
                      f"action {pn['proposed_action']} / {po['proposed_action']}, "
                      f"real_incident Δ {abs(pn['real_incident'] - po['real_incident']):.3f}, "
                      f"severity Δ {abs(pn['severity'] - po['severity']):.2f}")

    out = SMOKE_API
    out.write_text(json.dumps({"incident": inc.id, "native_jev": n, "openrouter_jev": o}, indent=2, default=str))
    console.print(f"saved -> {rel(out)}")
    both = bool(n.get("ok") and o.get("ok"))
    console.print(Panel.fit("[green]both API paths answered the full schema[/green]" if both
                            else "[yellow]one or more paths need attention[/yellow]",
                            border_style="green" if both else "yellow"))
    return 0 if both else 1


if __name__ == "__main__":
    sys.exit(main())
