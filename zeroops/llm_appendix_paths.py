"""Locations for the technical appendix comparing Jev with general LLMs; main deliverables stay untouched.

Decision logs live in their own subfolder of work/results, so report.py and build_hub.py (which read
work/results/decisions_*.jsonl) never pick them up.
"""
from zeroops import paths

CODE = paths.SCRIPTS / "llm_appendix"
RESULTS = paths.RESULTS / "llm_appendix"
SCRATCH = paths.SCRATCH / "llm_appendix"     # --limit smoke runs; git-ignored with the rest of scratch/
SCORECARD = RESULTS / "scorecard.json"
OUTPUT = paths.DELIVERABLES / "appendix-jev-vs-llms"
DECK = OUTPUT / "Jev-vs-LLMs_technical-appendix.pptx"
DECK_PDF = OUTPUT / "Jev-vs-LLMs_technical-appendix.pdf"
DATA = OUTPUT / "data"
PREVIEWS = OUTPUT / "previews"
README = OUTPUT / "README.md"


def log(backend: str, condition: str, run: int = 1):
    """One JSONL decision log per backend, condition and repeat."""
    return RESULTS / f"{condition}_r{run}_{backend}.jsonl"
