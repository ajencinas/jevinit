#!/usr/bin/env python3
"""Run the ZeroOps incident autopilot over the corpus on chosen backends.

  ./jev/bin/python scripts/run_eval.py --backends all [--variants 4] [--limit N]

Backends: api (Jev native + OpenRouter), local (Laya + Kev if served), all.
Writes work/results/decisions_<backend>.jsonl. It does NOT write metrics.json: scripts/report.py
is the only writer of metrics/report/demo payloads, so they always come from one pass over
the current decision files.

Safety rails:
- every record carries the corpus fingerprint, so report.py can refuse stale files;
- --limit runs go to work/results/scratch/ and never overwrite the full decision files;
- if every call for a backend failed, the existing decision file is kept and the failed
  run is written to work/results/scratch/ instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from zeroops.adapters import api_adapters, local_adapters  # noqa: E402
from zeroops.corpus import corpus_fingerprint, generate_corpus  # noqa: E402
from zeroops.metrics import compute_metrics  # noqa: E402
from zeroops.orchestrator import run_incident  # noqa: E402
from zeroops.paths import ENV, RESULTS, SCRATCH, decisions, rel, scratch_decisions  # noqa: E402

console = Console(width=150)
load_dotenv(ENV)


def build_adapters(which: str):
    out = []
    if which in ("api", "all"):
        out += api_adapters()
    if which in ("local", "all"):
        out += local_adapters()
    return out


def _fmt(v, spec: str = ".0f", none: str = "-") -> str:
    return none if v is None else format(v, spec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", choices=["api", "local", "all"], default="api")
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap incidents per backend (0 = all); output goes to work/results/scratch/")
    ap.add_argument("--only", default="", help="comma list of adapter names to keep")
    args = ap.parse_args()

    full = generate_corpus(n_variants=args.variants)
    version = corpus_fingerprint(full)
    corpus = full[: args.limit] if args.limit else full
    console.print(f"corpus: [bold]{len(corpus)}[/bold] incidents "
                  f"({len({i.archetype for i in corpus})} archetypes), version {version}")

    adapters = build_adapters(args.backends)
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        adapters = [a for a in adapters if a.name in keep]
    if not adapters:
        console.print("[red]No backends available[/red]")
        return 2
    console.print(f"backends: {[a.name for a in adapters]}\n")

    RESULTS.mkdir(exist_ok=True)
    all_metrics: dict[str, dict] = {}
    any_failed = False

    for adapter in adapters:
        console.rule(f"[bold]{adapter.name}[/bold]")
        records = []
        for i, inc in enumerate(corpus, 1):
            rec = run_incident(adapter, inc, corpus_version=version)
            records.append(rec)
            if rec.get("error"):
                console.print(f"  [{i:>2}/{len(corpus)}] {inc.id} [red]ERR {rec['error'][:70]}[/red]",
                              highlight=False)
                continue
            amark = "ok" if rec["correct"]["action"] else "X "
            console.print(
                f"  [{i:>2}/{len(corpus)}] {inc.id} {inc.archetype:<19} "
                f"gt={inc.ground_truth['correct_action']:<12} pred={rec['pred']['proposed_action']:<12} "
                f"{amark} {rec['decision']['outcome']:<8} {rec['latency_ms']:.0f}ms", highlight=False)

        body = "\n".join(json.dumps(r) for r in records) + "\n"
        all_failed = all(r.get("error") for r in records)
        if args.limit or all_failed:
            SCRATCH.mkdir(exist_ok=True)
            tag = f"limit{args.limit}" if args.limit else "failed"
            out = scratch_decisions(adapter.name, tag)
            if all_failed:
                any_failed = True
                console.print(f"  [red]every call failed; existing results kept[/red]")
        else:
            out = decisions(adapter.name)
        out.write_text(body)
        all_metrics[adapter.name] = compute_metrics(records)
        console.print(f"  saved -> {rel(out)}\n")

    table = Table(title="This run (run scripts/report.py to refresh metrics.json and report.md)")
    for col in ["backend", "n", "err", "cat%", "action%", "auto", "unsafe auto",
                "missed real", "p50 ms"]:
        table.add_column(col, justify="right" if col != "backend" else "left")
    for name, m in all_metrics.items():
        t, a, lat = m["decision_quality_pct"], m["autonomy"], m["latency_ms"]
        table.add_row(name, str(m["n"]), str(m["errors"]), _fmt(t["failure_category"]),
                      _fmt(t["action"]), str(a["auto"]), str(a["unsafe_auto"]),
                      str(a["missed_incidents"]), _fmt(lat["p50"]))
    console.print(table)
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
