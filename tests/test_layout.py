"""Project layout: every output lives in outputs/, paths come from zeroops/paths.py, the
generated pages' relative links resolve, and outputs/README.md lists every numbered file.

Offline: reads the files on disk only.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from zeroops import paths

# Built from pieces so this file doesn't trip its own check.
OLD_DIR = "dem" + "o"
OLD_PATH = re.compile(r"(?<!\w)" + OLD_DIR + r"/|[\"']" + OLD_DIR + r"[\"']")


def _code_files() -> list[Path]:
    files = [*paths.SCRIPTS.glob("*.py"), *paths.SCRIPTS.glob("*.sh"),
             *paths.TESTS.glob("*.py"), *paths.PACKAGE.glob("*.py")]
    return sorted(files)


def test_no_code_refers_to_the_old_output_folder():
    hits = []
    for f in _code_files() + [paths.README, *paths.CONTENT.iterdir()]:
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if OLD_PATH.search(line):
                hits.append(f"{paths.rel(f)}:{i}: {line.strip()[:120]}")
    assert not hits, "old output folder still referenced:\n" + "\n".join(hits)


def test_old_folders_are_gone():
    assert not (paths.ROOT / OLD_DIR).exists()
    assert not (paths.ROOT / "data").exists()
    for pre_bucket in ("deliverables", "content", "research", "results", "video"):
        assert not (paths.ROOT / pre_bucket).exists(), f"{pre_bucket}/ should live under a bucket"


def test_scripts_take_paths_from_zeroops_paths():
    """No script joins the project root with a folder name itself; zeroops/paths.py does."""
    joined = re.compile(r"\bROOT\s*/\s*[\"']")
    exempt = {paths.PACKAGE / "paths.py", Path(__file__).resolve()}  # this file checks for old folders
    offenders = [paths.rel(f) for f in _code_files()
                 if f.suffix == ".py" and f.resolve() not in exempt and joined.search(f.read_text())]
    assert not offenders, offenders


# ---------------------------------------------------------------- links in the generated pages

class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.links.append(v)


def _relative_links(page: Path) -> list[str]:
    p = _Links()
    p.feed(page.read_text())
    out = []
    for link in p.links:
        u = urlsplit(link)
        if u.scheme or u.netloc or link.startswith("#") or link.startswith("data:"):
            continue
        out.append(link)
    return out


PAGES = [paths.HUB, paths.LAB_PAGE, paths.ONE_INCIDENT_PAGE, paths.DASHBOARD_PAGE]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: paths.rel(p))
def test_relative_links_resolve(page):
    assert page.exists(), f"{paths.rel(page)} not built"
    missing = []
    for link in _relative_links(page):
        target = (page.parent / unquote(urlsplit(link).path)).resolve()
        if not target.exists():
            missing.append(link)
        # a page served from outputs/ can't reach anything outside it
        elif paths.DELIVERABLES.resolve() not in (target, *target.parents):
            missing.append(f"{link} (outside outputs/)")
    assert not missing, f"{paths.rel(page)}: {missing}"


def test_hub_links_the_numbered_files_and_the_pages():
    links = set(_relative_links(paths.HUB))
    for p in (paths.DECK_V4, paths.QUESTIONS, paths.VIDEO_DEMO,
              paths.REPORT, paths.LAB_PAGE, paths.ONE_INCIDENT_PAGE, paths.DASHBOARD_PAGE):
        assert paths.href(p) in links, paths.href(p)


@pytest.mark.parametrize("page", [paths.LAB_PAGE, paths.ONE_INCIDENT_PAGE], ids=lambda p: paths.rel(p))
def test_pages_link_back_to_the_hub(page):
    assert "../index.html" in _relative_links(page)


# ---------------------------------------------------------------- outputs/README.md

def test_readme_index_lists_every_numbered_file():
    text = paths.DELIVERABLES_README.read_text()
    numbered = sorted(p.name for p in paths.DELIVERABLES.glob("[0-9]_*") if p.is_file())
    assert numbered, "no numbered deliverables found"
    missing = [n for n in numbered if f"[{n}]({n})" not in text]
    assert not missing, missing


def test_numbered_files_match_zeroops_paths():
    expected = {p.name for p in (paths.DECK_V4, paths.DECK_V4_PDF, paths.QUESTIONS, paths.VIDEO_DEMO,
                                 paths.REPORT)}
    found = {p.name for p in paths.DELIVERABLES.glob("[0-9]_*")}
    assert found <= expected, f"numbered files not in zeroops/paths.py: {sorted(found - expected)}"


def test_project_root_holds_no_outputs():
    allowed = {"inputs", "work", "outputs", "zeroops", "scripts", "tests",
               "third_party", "jev", "README.md", "CHANGES.md", "requirements.txt", ".env", ".env.example",
               ".gitignore", ".pytest_cache"}
    stray = sorted(p.name for p in paths.ROOT.iterdir() if p.name not in allowed)
    assert not stray, f"unexpected files in the project root: {stray}"
