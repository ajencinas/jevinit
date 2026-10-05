#!/usr/bin/env python3
"""Run the ZeroOps pipeline end to end.

  ./jev/bin/python scripts/run_all.py [--skip-api] [--skip-local] [--start-kev] [--skip-demo]
                                      [--race-live] [--videos] [--variants 4] [--dry-run]

Steps, in order:
  1. run_eval.py --backends api      both Jev endpoints (paid, cents)         skip: --skip-api
  2. run_eval.py --backends local    Laya, then Kev if its server is up (GPU)  skip: --skip-local
  3. report.py                       metrics.json, facts.json, demo_data.json, outputs/7_results-report.md
  4. build_v4.py (the discussion deck, its PDF and slide images; skipped with a note if LibreOffice or
     pdftoppm is missing), build_questions.py, build_lab.py,
     build_demo.py (unless --skip-demo)
  5. build_race.py                   re-renders outputs/one-incident from work/results/race_trace.json;
                                     --race-live re-records it first (paid, one call each)
  6. only with --videos: build_video.py (ElevenLabs TTS, paid; unchanged segments are cached), then
                                     a HyperFrames render of video/demo into outputs/4_demo.mp4
  7. build_hub.py                    outputs/index.html, outputs/README.md,
                                     outputs/docs/, README Results block

Every path comes from zeroops/paths.py.

Offline rebuild from the saved decision logs: --skip-api --skip-local.

run_eval.py exit codes: 0 ok; 2 means no backend was available (no API key, say), which is
reported and skipped; anything else stops the pipeline (run_eval.py keeps the existing decision
logs when every call for a backend fails). A Kev server started by this script (--start-kev) is
always stopped again as soon as the Kev run ends, including on failure or Ctrl-C.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zeroops import paths  # noqa: E402
from zeroops.adapters import kev_available  # noqa: E402

ROOT, SCRIPTS = paths.ROOT, paths.SCRIPTS

PY = sys.executable
NO_BACKENDS = 2  # run_eval.py: "No backends available"
# Node 22 on the author's machine; override with $NODE22_BIN elsewhere.
DEFAULT_NODE_BIN = "/media/alfonso/shared/jev_local/node22/bin"
# Same HyperFrames version as video/*/package.json; override with $HYPERFRAMES_PKG.
HYPERFRAMES = os.getenv("HYPERFRAMES_PKG", "hyperframes@0.8.114")
VIDEOS = [  # (builder, HyperFrames project, rendered video in outputs/)
    ("build_video.py", paths.DEMO_SRC, paths.VIDEO_DEMO),
]


class StepFailed(RuntimeError):
    pass


class Runner:
    def __init__(self, dry: bool):
        self.dry = dry
        self.notes: list[str] = []      # skipped on purpose or unavailable; not an error
        self.problems: list[str] = []   # something that was asked for did not happen

    def cmd(self, argv: list[str], *, cwd: Path | None = None, env: dict | None = None) -> int:
        where = f"(in {cwd.relative_to(ROOT)}) " if cwd else ""
        root = f"{ROOT}{os.sep}"
        shown = " ".join(shlex.quote("python" if a == PY else a.removeprefix(root)) for a in argv)
        print(f"\n$ {where}{shown}", flush=True)
        if self.dry:
            return 0
        return subprocess.run(argv, cwd=cwd, env={**os.environ, **(env or {})}).returncode

    def script(self, name: str, *args: str, env: dict | None = None, check: bool = True) -> int:
        rc = self.cmd([PY, str(SCRIPTS / name), *args], env=env)
        if check and rc != 0:
            raise StepFailed(f"{' '.join([name, *args])} exited {rc}")
        return rc

    def evaluate(self, label: str, *args: str, env: dict | None = None) -> None:
        rc = self.script("run_eval.py", *args, env=env, check=False)
        if rc == NO_BACKENDS:
            note = (f"{label}: no backend available (API key or local model missing); "
                    f"the saved decision logs were used")
            print(f"[note] {note}")
            self.notes.append(note)
        elif rc != 0:
            raise StepFailed(f"run_eval.py ({label}) exited {rc}. The saved decision logs were kept. "
                             f"Fix the backend, or re-run with --skip-api / --skip-local to rebuild "
                             f"from the saved logs.")


def find_node_bin() -> str | None:
    for cand in (os.getenv("NODE22_BIN"), DEFAULT_NODE_BIN):
        if cand and (Path(cand) / "npx").exists():
            return cand
    found = shutil.which("npx")
    return str(Path(found).parent) if found else None


def start_kev_and_wait(r: Runner, timeout: int = 240) -> bool:
    r.cmd([str(SCRIPTS / "serve_kev.sh")])
    if r.dry:
        return True
    for _ in range(max(1, timeout // 3)):
        if kev_available():
            print("Kev is up.")
            return True
        time.sleep(3)
    return False


def run_local(r: Runner, args: argparse.Namespace, v: list[str]) -> None:
    # Laya first, on the GPU, before Kev is resident.
    r.evaluate("Laya", "--backends", "local", "--only", "laya_local", *v,
               env={"LAYA_MODEL": os.getenv("LAYA_MODEL", "typed-decisions")})
    kev_up = kev_available()
    started = False
    try:
        if not kev_up and args.start_kev:
            started = True  # set first: a half-started server must still be stopped
            kev_up = start_kev_and_wait(r)
            if not kev_up:
                r.problems.append("Kev did not come up within the timeout (see /tmp/kev_serve.log); "
                                  "its saved decision log was used")
        if kev_up:
            r.evaluate("Kev", "--backends", "local", "--only", "kev", *v)
        elif not args.start_kev:
            r.notes.append("Kev server not up, so Kev was not re-run (pass --start-kev, or start "
                           "scripts/serve_kev.sh first); its saved decision log was used")
    finally:
        if started:
            r.cmd([str(SCRIPTS / "stop_kev.sh")])


def render_videos(r: Runner, node_bin: str) -> None:
    env = {"PATH": f"{node_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    npx = str(Path(node_bin) / "npx")
    for builder, project, out in VIDEOS:
        if builder:
            r.script(builder)
        # -o relative to the project dir, as HyperFrames resolves it from there
        for step in (["check"], ["render", "-o", paths.href(out, project)]):
            rc = r.cmd([npx, "--yes", HYPERFRAMES, *step], cwd=project, env=env)
            if rc != 0:
                raise StepFailed(f"hyperframes {step[0]} failed in {project.relative_to(ROOT)} (exit {rc})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--skip-api", action="store_true",
                    help="don't re-run the Jev endpoints (paid); use the saved decision logs")
    ap.add_argument("--skip-local", action="store_true",
                    help="don't re-run Laya and Kev (GPU); use the saved decision logs")
    ap.add_argument("--start-kev", action="store_true",
                    help="start the Kev server after Laya if it isn't up, and stop it after the Kev run")
    ap.add_argument("--skip-demo", action="store_true",
                    help="don't rebuild the dashboard (video/dashboard-loop, outputs/dashboard)")
    ap.add_argument("--race-live", action="store_true",
                    help="re-record the race page: one paid call each to Jev and a chat model")
    ap.add_argument("--videos", action="store_true",
                    help="regenerate the two voice-overs (ElevenLabs, paid) and render all three videos")
    ap.add_argument("--dry-run", action="store_true", help="print the steps without running them")
    args = ap.parse_args()
    v = ["--variants", str(args.variants)]

    builders = ["build_v4.py", "build_questions.py", "build_lab.py"]
    if not args.skip_demo:
        builders.append("build_demo.py")
    race = ["build_race.py", "--live"] if args.race_live else ["build_race.py"]

    # Check everything up front, so a missing script doesn't fail after the paid steps.
    needed = ["run_eval.py", "report.py", *builders, "build_race.py", "build_hub.py"]
    if args.videos:
        needed += [b for b, _, _ in VIDEOS if b]
    missing = [s for s in needed if not (SCRIPTS / s).exists()]
    if missing:
        print(f"missing scripts: {', '.join(missing)}; nothing was run")
        return 1
    node_bin = find_node_bin() if args.videos else None
    if args.videos and not node_bin:
        print("--videos needs Node 22 with npx: set NODE22_BIN, or put npx on PATH; nothing was run")
        return 1

    r = Runner(dry=args.dry_run)
    try:
        if args.skip_api:
            r.notes.append("API backends not re-run (--skip-api)")
        else:
            r.evaluate("Jev API backends", "--backends", "api", *v)
        if args.skip_local:
            r.notes.append("local backends not re-run (--skip-local)")
        else:
            run_local(r, args, v)

        r.script("report.py")
        for b in builders:
            r.script(b)
        r.script(*race)
        if args.videos:
            render_videos(r, node_bin)
        r.script("build_hub.py")
    except StepFailed as e:
        print(f"\nStopped: {e}. Later steps were not run.")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Later steps were not run.")
        return 130

    print("\n" + ("Dry run: nothing was executed." if args.dry_run else "Done."))
    for n in r.notes:
        print(f"  note: {n}")
    for p in r.problems:
        print(f"  problem: {p}")
    if not args.dry_run:
        print(f"Outputs: {paths.rel(paths.DELIVERABLES)}/ (start with {paths.rel(paths.DELIVERABLES_README)} "
              f"or {paths.rel(paths.HUB)}).")
    return 1 if r.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
