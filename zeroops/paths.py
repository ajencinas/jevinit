"""Every file and folder the scripts and tests read or write, in one place.

Layout (three buckets, plus the code at the top level):
  inputs/        storyline (claims.json, questions.template.md), inputs/research/ and reference/
  work/          pipeline intermediates: work/results/ (decision logs and what report.py derives
                 from them) and video/ (HyperFrames sources, rendered into outputs/)
  outputs/       everything a reader opens, numbered in reading order, plus the hub page,
                 the interactive pages, previews and copies of the research files
  zeroops/ scripts/ tests/   the process: the harness, the builders and the tests
  jev/           the Python virtualenv (not part of the project; recreated with python -m venv)

Builders and tests import these constants instead of joining string literals, so moving a
file means editing this module only.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- outputs/
DELIVERABLES = ROOT / "outputs"
HUB = DELIVERABLES / "index.html"
DELIVERABLES_README = DELIVERABLES / "README.md"
QUESTIONS = DELIVERABLES / "3_open-questions-and-next-steps.md"
VIDEO_DEMO = DELIVERABLES / "4_demo.mp4"
REPORT = DELIVERABLES / "7_results-report.md"
DECK_V4 = DELIVERABLES / "1_ZeroOps-Jev_v4.pptx"
DECK_V4_PDF = DELIVERABLES / "1_ZeroOps-Jev_v4.pdf"

LAB_DIR = DELIVERABLES / "lab"
LAB_PAGE = LAB_DIR / "index.html"
ONE_INCIDENT_DIR = DELIVERABLES / "one-incident"
ONE_INCIDENT_PAGE = ONE_INCIDENT_DIR / "index.html"
# A copy of the dashboard-loop composition, so the hub can link it while only outputs/ is served.
DASHBOARD_DIR = DELIVERABLES / "dashboard"
DASHBOARD_PAGE = DASHBOARD_DIR / "index.html"

PREVIEWS = DELIVERABLES / "previews"
PREVIEWS_DECK = PREVIEWS / "deck"          # slide-01.png ... one image per slide
PREVIEWS_VIDEO = PREVIEWS / "video"        # frames from the three videos
PREVIEWS_PAGES = PREVIEWS / "pages"
PREVIEW_LAB = PREVIEWS_PAGES / "lab.png"
PREVIEW_ONE_INCIDENT = PREVIEWS_PAGES / "one-incident.png"
DECK_PREVIEW_PREFIX = "slide"              # pdftoppm -png <pdf> v4/previews/slide -> slide-01.png

DOCS = DELIVERABLES / "docs"               # copies of research files, made by build_hub.py
DOCS_RESEARCH = DOCS / "research"

# ---------------------------------------------------------------- work/video/ (HyperFrames sources)
VIDEO_SRC = ROOT / "work" / "video"
DEMO_SRC = VIDEO_SRC / "showcase"
DEMO_ASSETS = DEMO_SRC / "assets"
DEMO_PAGE = DEMO_SRC / "index.html"
LOOP_SRC = VIDEO_SRC / "dashboard-loop"       # the interactive dashboard page (not a video)
LOOP_PAGE = LOOP_SRC / "index.html"

# ---------------------------------------------------------------- work/results/ (raw run data)
RESULTS = ROOT / "work" / "results"
SCRATCH = RESULTS / "scratch"
DECISIONS_GLOB = "decisions_*.jsonl"
FACTS = RESULTS / "facts.json"
METRICS = RESULTS / "metrics.json"
DEMO_DATA = RESULTS / "demo_data.json"
LAB_DATA = RESULTS / "lab_data.json"
RACE_TRACE = RESULTS / "race_trace.json"
DEMO_SEGMENTS = RESULTS / "demo_segments.json"
SMOKE_API = RESULTS / "smoke_api.json"

# ---------------------------------------------------------------- inputs/ (source text, research, reference)
CONTENT = ROOT / "inputs"
CLAIMS = CONTENT / "claims.json"
QUESTIONS_TEMPLATE = CONTENT / "questions.template.md"
RESEARCH = CONTENT / "research"
RESEARCH_README = RESEARCH / "README.md"
# Research files the hub links to (copied into outputs/docs/research/).
RESEARCH_DOCS = ("README.md", "landscape-synthesis.md", "independent-review-claude.md",
                 "industry-evidence-kimi-online.md",
                 "build-vs-buy-gemini-openai.txt", "composable-stack-and-compliance-gemini-openai.txt")

# ---------------------------------------------------------------- code and config
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
PACKAGE = ROOT / "zeroops"
README = ROOT / "README.md"
ENV = ROOT / ".env"


def decisions(backend: str) -> Path:
    """work/results/decisions_<backend>.jsonl"""
    return RESULTS / f"decisions_{backend}.jsonl"


def scratch_decisions(backend: str, tag: str) -> Path:
    """work/results/scratch/decisions_<backend>.<tag>.jsonl (--limit runs and failed runs)."""
    return SCRATCH / f"decisions_{backend}.{tag}.jsonl"


def research_doc_copy(name: str) -> Path:
    """Where build_hub.py copies inputs/research/<name> for the hub's links."""
    return DOCS_RESEARCH / name


def rel(p: Path) -> str:
    """Path relative to the project root, as cited in copy ("outputs/7_results-report.md")."""
    return p.relative_to(ROOT).as_posix()


def href(p: Path, start: Path = DELIVERABLES) -> str:
    """Relative link from the folder `start` (default: outputs/, where the hub lives) to `p`."""
    return Path(os.path.relpath(p, start)).as_posix()
