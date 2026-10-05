#!/usr/bin/env python3
"""ZeroOps triage in the terminal: one incident, the model's typed answers, the gate.

Reads a saved decision by default (instant, offline, no cost):
  ./jev/bin/python scripts/demo_cli.py --incident INC-0011
  ./jev/bin/python scripts/demo_cli.py --archetype security_incident --backend kev
  ./jev/bin/python scripts/demo_cli.py --random --backend jev_openrouter

Or calls the backend now (--live). Jev native and Jev via OpenRouter are paid API calls
(about $0.00006 each); Kev needs its local server (scripts/serve_kev.sh); Laya runs in-process.
  ./jev/bin/python scripts/demo_cli.py --live --backend jev_native --incident INC-0001
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console, Group  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

from zeroops.facts import LABELS, LOCAL, ORDER, parsed_from_pred  # noqa: E402
from zeroops.paths import ENV, FACTS, decisions  # noqa: E402
from zeroops.policy import AUTO_ACTIONS, explain  # noqa: E402
from zeroops.schema import ACCEPTABLE_ACTIONS  # noqa: E402

console = Console()
CLOSE = 0.05

OUTCOME_STYLE = {"AUTO": "bold green", "ESCALATE": "bold red", "OBSERVE": "bold grey62"}
OUTCOME_TEXT = {"AUTO": "act alone, nobody paged", "ESCALATE": "page a person", "OBSERVE": "log only"}


def bar(v: float, width: int = 18) -> str:
    v = max(0.0, min(1.0, v))
    return "█" * round(v * width) + "·" * (width - round(v * width))


def question_rows(p: dict) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    t.add_column("question", style="bold")
    t.add_column("type", style="dim")
    t.add_column("answer")
    t.add_column("probability", style="cyan")

    def noul(label, val):
        t.add_row(label, "yes-prob.", f"{val:.2f}", f"{bar(val)} {val:.2f}")

    def choice(label, val, conf):
        t.add_row(label, "choice", str(val), f"{bar(conf)} {conf:.2f}" if conf is not None else "")

    def score(label, val, conf):
        t.add_row(label, "score", val, f"{bar(conf)} {conf:.2f}" if conf is not None else "")

    noul("real_incident", p["real_incident"])
    choice("failure_category", p["failure_category"], p["category_confidence"])
    choice("suspect_component", p["suspect_component"], None)
    choice("root_cause", p["root_cause"], None)
    noul("deploy_correlated", p["deploy_correlated"])
    score("severity", f"{p['severity']:.2f} / 3", p["severity_confidence"])
    score("blast_radius", f"{p['blast_radius']:.2f} / 3", None)
    noul("customer_impact", p["customer_impact"])
    noul("safe_to_autorollback", p["safe_to_autorollback"])
    choice("proposed_action", p["proposed_action"], p["action_confidence"])
    score("action_risk", f"{p['action_risk']:.2f} / 2", None)
    noul("needs_page", p["needs_page"])
    return t


def gate_table(pred: dict, th: dict) -> Table:
    """Every gate check with value, threshold, result and margin, from zeroops.policy.explain."""
    parsed = parsed_from_pred(pred)
    t = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    t.add_column("check", style="bold")
    t.add_column("value", justify="right")
    t.add_column("threshold", style="dim")
    t.add_column("", justify="center")
    t.add_column("margin", justify="right", style="dim")
    if parsed.missing:
        t.add_row("all answers present", ", ".join(parsed.missing), "", Text("FAIL", style="bold red"), "")
    for c in explain(parsed, th):
        mark = Text("PASS", style="bold green") if c["passed"] else Text("FAIL", style="bold red")
        if c["passed"] and abs(c["margin"]) <= CLOSE:
            mark.append(" close", style="yellow")
        t.add_row(c["check"], f"{c['value']:.2f}", f"{c['op']} {c['threshold']:g}", mark, f"{c['margin']:+.2f}")
        if c["check"] == "real_incident":
            ok = parsed.proposed_action in AUTO_ACTIONS
            t.add_row("action may be automated", parsed.proposed_action or "—", "/".join(sorted(AUTO_ACTIONS)),
                      Text("PASS", style="bold green") if ok else Text("FAIL", style="bold red"), "")
    return t


def cost_text(rec: dict) -> str:
    backend, cost = rec["backend"], rec.get("cost_usd")
    if backend in LOCAL:
        return "no API fee (local GPU; GPU and power not costed)"
    if cost is not None:
        return f"${cost:.6f} billed"
    facts_f = FACTS
    if facts_f.exists():
        b = json.loads(facts_f.read_text())["backends"].get(backend) or {}
        if b.get("cost_per_1k_usd"):
            return (f"not returned by this API; about ${b['cost_per_1k_usd'] / 1000:.6f} per call "
                    f"estimated at OpenRouter's billed rate")
    return "not returned by this API"


def render(rec: dict, th: dict) -> None:
    pred, gt, dec = rec["pred"], rec["ground_truth"], rec["decision"]
    outcome = dec["outcome"]
    label = LABELS.get(rec["backend"], rec["backend"])
    console.rule(f"[bold]ZeroOps triage · {rec['incident_id']} · {rec['archetype']}[/bold]")
    console.print(Panel(rec["state"].strip(), title="[bold]incident text[/bold]",
                        border_style="grey37", title_align="left"))
    console.print(Panel(question_rows(pred), title=f"[bold]{label}: 12 typed answers from one call[/bold]",
                        border_style="cyan", title_align="left"))
    console.print(Panel(gate_table(pred, th), title="[bold]Gate (zeroops/policy.py, checked in order)[/bold]",
                        border_style="magenta", title_align="left"))
    line = Text()
    line.append("outcome: ", style="dim")
    line.append(outcome, style=OUTCOME_STYLE.get(outcome, "bold"))
    line.append(f" ({OUTCOME_TEXT.get(outcome, '')})   action: {dec['action']}")
    proposed = pred["proposed_action"]
    if proposed == gt["correct_action"]:
        match, style = "exact match", "green"
    elif proposed in ACCEPTABLE_ACTIONS.get(rec["archetype"], set()):
        match, style = "on the acceptable list written after the first run", "yellow"
    else:
        match, style = "different", "red"
    line.append(f"\nour label: {gt['correct_action']} ({'safe' if gt['auto_safe'] else 'not safe'} to automate)"
                f" · model's action {proposed}: {match}", style=style)
    console.print(Panel(Group(line, Text(dec["rationale"], style="dim")),
                        border_style=OUTCOME_STYLE.get(outcome, "white").split()[-1]))
    console.print(f"[dim]backend={rec['backend']}  model={rec.get('model', '')}  "
                  f"latency={rec['latency_ms']:.0f} ms  cost={cost_text(rec)}[/dim]\n")


def pick_saved(backend: str, incident: str | None, archetype: str | None, rnd: bool) -> dict:
    f = decisions(backend)
    if not f.exists():
        console.print(f"[red]no saved decisions for backend '{backend}' ({f.name}). "
                      f"Run scripts/run_eval.py first, or pass --live.[/red]")
        sys.exit(2)
    recs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    recs = [r for r in recs if not r.get("error")]
    if incident:
        recs = [r for r in recs if r["incident_id"] == incident]
    elif archetype:
        recs = [r for r in recs if r["archetype"] == archetype]
    if not recs:
        console.print("[red]no matching incident[/red]")
        sys.exit(2)
    return random.choice(recs) if rnd else recs[0]


def live_adapter(backend: str):
    from zeroops import adapters

    if backend == "jev_native":
        return adapters.native_adapter()
    if backend == "jev_openrouter":
        return adapters.openrouter_adapter()
    if backend == "kev":
        if not adapters.kev_available():
            console.print("[red]Kev server is not running on "
                          f"127.0.0.1:{os.getenv('KEV_PORT', '8009')}; start it with scripts/serve_kev.sh[/red]")
            sys.exit(2)
        return adapters.kev_adapter()
    if backend == "laya_local":
        return adapters.LayaLocalAdapter(default_model=os.getenv("LAYA_ROUTER_DEFAULT"),
                                         predict_model=os.getenv("LAYA_MODEL"),
                                         device=os.getenv("LAYA_DEVICE"))
    raise SystemExit(f"unknown backend {backend}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="jev_native", choices=ORDER)
    ap.add_argument("--incident", default=None)
    ap.add_argument("--archetype", default=None)
    ap.add_argument("--random", action="store_true")
    ap.add_argument("--live", action="store_true", help="call the backend now instead of reading saved results")
    args = ap.parse_args()

    from zeroops.policy import DEFAULT_THRESHOLDS

    th = DEFAULT_THRESHOLDS
    if args.live:
        from dotenv import load_dotenv

        from zeroops.corpus import corpus_fingerprint, generate_corpus
        from zeroops.orchestrator import run_incident

        load_dotenv(ENV)
        corpus = generate_corpus(n_variants=4)
        if args.incident:
            inc = next((i for i in corpus if i.id == args.incident), None)
        elif args.archetype:
            inc = next((i for i in corpus if i.archetype == args.archetype), None)
        else:
            inc = random.choice(corpus)
        if inc is None:
            console.print("[red]no matching incident in the corpus[/red]")
            return 2
        rec = run_incident(live_adapter(args.backend), inc, th, corpus_version=corpus_fingerprint(corpus))
        if rec.get("error"):
            console.print(f"[red]live call failed: {rec['error']}[/red]")
            return 1
    else:
        rec = pick_saved(args.backend, args.incident, args.archetype, args.random)

    render(rec, th)
    ok = ACCEPTABLE_ACTIONS.get(rec["archetype"], set())
    console.print(f"[dim]acceptable actions for {rec['archetype']} (lenient list, written after the "
                  f"first run): {', '.join(sorted(ok))}[/dim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
