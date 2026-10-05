#!/usr/bin/env python3
"""Run Jev and the comparison LLMs over every condition; one JSONL decision log per backend, condition and run.

  ./jev/bin/python scripts/llm_appendix/run.py --dry-run          # calls and estimated cost, no requests
  ./jev/bin/python scripts/llm_appendix/run.py --limit 2          # smoke run into work/results/scratch/llm_appendix
  ./jev/bin/python scripts/llm_appendix/run.py --max-usd 20       # the full run (resumes where it stopped)

Paid: OpenRouter for the LLMs, the TypeSafe API for Jev. Logs go to work/results/llm_appendix/, never to the
main work/results/decisions_*.jsonl that the deck reads. Each backend runs its calls one after another, on
its own keep-alive connection; backends run side by side.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE)]
from dotenv import load_dotenv  # noqa: E402

from zeroops import paths  # noqa: E402
from zeroops import llm_appendix_paths as loc  # noqa: E402
from zeroops.adapters import native_adapter  # noqa: E402
from zeroops.corpus import corpus_fingerprint  # noqa: E402
from zeroops.orchestrator import run_incident  # noqa: E402
from chat import ChatAdapter  # noqa: E402
from conditions import CONDITIONS, Shuffled, incidents  # noqa: E402

JEV = "jev_native"
# backend -> (OpenRouter model id, $ per M input, $ per M output, ask for logprobs, typical tokens in/out per call)
MODELS = {
    "claude-sonnet-5.5": ("anthropic/claude-sonnet-5.5", 2.0, 10.0, False, (3900, 265)),
    "gpt-6.1-sol": ("openai/gpt-6.1-sol", 2.0, 10.0, False, (1840, 250)),
    "gemini-3.8-flash": ("google/gemini-3.8-flash", 0.75, 3.75, False, (1340, 330)),
    "gpt-6-luna": ("openai/gpt-6-luna", 0.10, 0.50, False, (1840, 185)),
    "qwen3.8-flash": ("qwen/qwen3.8-flash", 0.15, 0.47, True, (1330, 330)),
}
JEV_PRICE_IN = 0.042            # $ per M input tokens, list price; output is not billed
BACKENDS = (JEV, *MODELS)
RUNS = [("base", 1), ("base", 2), ("base", 3), ("shuffled", 1), ("injected", 1), ("harder", 1)]


def adapter(backend: str, key: str):
    if backend == JEV:
        a = native_adapter()
        a.max_attempts = 3
        return a
    model, *_, logprobs, _ = MODELS[backend]
    return ChatAdapter(backend, model, key, logprobs=logprobs)


def estimate(backend: str, calls: int) -> float:
    if backend == JEV:
        return calls * 1350 * JEV_PRICE_IN / 1e6
    _, pin, pout, _, (tin, tout) = MODELS[backend]
    return calls * (tin * pin + tout * pout) / 1e6


def read_log(path: Path) -> dict[str, dict]:
    """Answered records already in a log, by incident id (failed ones are retried)."""
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error"):
                    done[r["incident_id"]] = r
    return done


class Budget:
    def __init__(self, limit: float, spent: float):
        self.limit, self.spent, self.lock = limit, spent, threading.Lock()

    def add(self, usd: float | None) -> bool:
        with self.lock:
            self.spent += usd or 0.0
            return self.spent < self.limit


def spent_so_far(folder: Path) -> float:
    total = 0.0
    for f in folder.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                total += json.loads(line).get("cost_usd") or 0.0
    return total


def run_backend(backend: str, key: str, runs, folder: Path, limit: int | None, budget: Budget, out: dict):
    a = adapter(backend, key)
    for condition, run in runs:
        incs = incidents(condition)[:limit] if limit else incidents(condition)
        version = corpus_fingerprint(incs)
        path = folder / loc.log(backend, condition, run).name
        done = read_log(path)
        path.write_text("".join(json.dumps(r) + "\n" for r in done.values()))
        wrapped = Shuffled(a) if condition == "shuffled" else a
        n_err = 0
        with path.open("a") as fh:
            for inc in incs:
                if inc.id in done:
                    continue
                rec = run_incident(wrapped, inc, corpus_version=version)
                rec.update(condition=condition, run=run)
                last = getattr(a, "last", None)
                if last is not None:
                    rec["llm"] = {k: v for k, v in last.items() if k not in ("answers", "content")}
                    rec["llm"]["stated"] = {q: v.get("stated") for q, v in (last.get("answers") or {}).items()
                                            if "stated" in v}
                n_err += bool(rec.get("error"))
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                if not budget.add(rec.get("cost_usd")):
                    out[backend] = f"stopped at the ${budget.limit:.2f} cap during {condition} r{run}"
                    return
        print(f"  {backend:18} {condition:8} r{run}: {len(incs) - n_err}/{len(incs)} answered", flush=True)
    out[backend] = "done"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", default=",".join(BACKENDS), help="comma-separated subset of: " + ", ".join(BACKENDS))
    ap.add_argument("--conditions", default=",".join(CONDITIONS), help="comma-separated subset of: " + ", ".join(CONDITIONS))
    ap.add_argument("--limit", type=int, help="first N incidents only; writes to the scratch subfolder")
    ap.add_argument("--max-usd", type=float, default=20.0, help="stop when billed spend in the log folder reaches this")
    ap.add_argument("--dry-run", action="store_true", help="print calls and estimated cost; make no requests")
    args = ap.parse_args()

    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    conds = {c.strip() for c in args.conditions.split(",") if c.strip()}
    unknown = [b for b in backends if b not in BACKENDS] + sorted(conds - set(CONDITIONS))
    if unknown:
        ap.error(f"unknown: {', '.join(unknown)}")
    runs = [(c, r) for c, r in RUNS if c in conds]
    folder = loc.SCRATCH if args.limit else loc.RESULTS
    per_backend = sum(len(incidents(c)[:args.limit] if args.limit else incidents(c)) for c, _ in runs)

    print(f"{len(backends)} backends x {len(runs)} runs = {per_backend * len(backends)} calls")
    for b in backends:
        print(f"  {b:18} {per_backend:4} calls  ~${estimate(b, per_backend):.2f}")
    print(f"  estimated total ~${sum(estimate(b, per_backend) for b in backends):.2f} (list prices, typical tokens)")
    if args.dry_run:
        return 0

    load_dotenv(paths.ENV)
    key = os.getenv("OPENROUTER_API") or os.getenv("OPENROUTER_API_KEY") or ""
    if any(b != JEV for b in backends) and not key:
        print("OPENROUTER_API is not set in .env; nothing was run")
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    budget = Budget(args.max_usd, spent_so_far(folder))
    print(f"billed so far in {paths.rel(folder)}: ${budget.spent:.4f}; cap ${args.max_usd:.2f}")
    out: dict[str, str] = {}
    threads = [threading.Thread(target=run_backend, args=(b, key, runs, folder, args.limit, budget, out))
               for b in backends]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for b in backends:
        print(f"{b:18} {out.get(b, 'failed (see traceback above)')}")
    print(f"billed in {paths.rel(folder)}: ${spent_so_far(folder):.4f}")
    return 0 if all(out.get(b) == "done" for b in backends) else 1


if __name__ == "__main__":
    raise SystemExit(main())
