"""The considerations/questions document is rendered from a template + work/results/facts.json."""
import importlib.util
import re

from zeroops import paths


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, paths.SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_template_renders_with_every_placeholder_filled():
    bq = _load("build_questions")
    out = bq.render(bq.TEMPLATE.read_text(), bq.values())
    assert "{{" not in out and "}}" not in out
    # all 12 considerations and 23 questions are present, in order
    assert re.findall(r"^### C(\d+)\.", out, re.M) == [str(i) for i in range(1, 13)]
    assert re.findall(r"^\*\*Q(\d+)\.", out, re.M) == [str(i) for i in range(1, 24)]


def test_rendered_numbers_follow_facts():
    import json
    bq = _load("build_questions")
    out = bq.render(bq.TEMPLATE.read_text(), bq.values())
    f = json.loads(paths.FACTS.read_text())
    jn = f["backends"]["jev_native"]
    assert f"{jn['action_exact']['pct']:.0f}%" in out
    assert f"{f['jev']['first_option_proposed']} times where our" in out
    assert f"at 0.80 the gate would have automated {[s for s in f['jev']['sensitivity'] if s['thresholds']['page_min'] == 0.8][0]['auto']}" in out


def test_no_banned_phrases_and_no_recommendation():
    bq = _load("build_questions")
    hub = _load("build_hub")
    out = bq.render(bq.TEMPLATE.read_text(), bq.values())
    hub.check_banned(out, paths.QUESTIONS.name)  # raises on a banned phrase
    assert "we recommend" not in out.lower()
