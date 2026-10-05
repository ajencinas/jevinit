#!/usr/bin/env python3
"""Build the v4 discussion edition (single story.json; deck only, no memo).

  ./jev/bin/python scripts/build_v4.py
Writes outputs/v4/ (or outputs/v4/build_NN if a build already exists).
Numbers from work/results/facts.json; the network example is read from the decision log.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zeroops import paths
from zeroops import v4_paths as loc
from zeroops.schema import Parsed
from zeroops.policy import explain
from build_cio_v2 import context, fill, digest, box, text, table, export_pdf, checks_rows

NAVY, TEAL, GREY, LIGHT = "142E42", "007F82", "596A76", "EFF4F6"


def rule(slide, y, x=.6, w=12.1, color="CCD7DD"):
    box(slide, x, y, w, .012, color)


def frame(slide, spec):
    box(slide, 0, 0, 13.333, .08, TEAL)
    text(slide, spec["section"].upper(), .6, .26, 12, .3, 10, TEAL, True)
    text(slide, spec["title"], .6, .72, 12.1, .95, 25, NAVY, True)
    if spec.get("subtitle"):
        text(slide, spec["subtitle"], .6, 1.66, 12.1, .42, 13, GREY)


def footer(slide, spec, index, sources):
    rule(slide, 6.5)
    text(slide, "For discussion \u00b7 October 2026", .6, 7.16, 5, .19, 8, GREY)
    for i, ref in enumerate(spec.get("refs", [])):
        shp = text(slide, ref, 7.6 + i * .55, 7.13, .5, .23, 9, GREY)
        shp.text_frame.paragraphs[0].runs[0].hyperlink.address = sources[ref]["url"]
    text(slide, str(index), 12.4, 7.13, .3, .23, 9, GREY)


def band(slide, spec, y):
    if spec.get("takeaway"):
        box(slide, .6, y, 12.13, .5, NAVY)
        text(slide, spec["takeaway"], .78, y + .1, 11.8, .35, 13, "FFFFFF", True)
        if spec.get("source"):
            text(slide, spec["source"], .6, y + .55, 12.1, .3, 8, GREY)


def network_example():
    recs = [json.loads(l) for l in paths.decisions("jev_native").read_text().splitlines() if l.strip()]
    order = ("dns_failure", "network_partition", "dependency_outage", "cert_expiry")
    r = None
    for a in order:
        r = next((x for x in recs if x["archetype"] == a), None)
        if r:
            break
    r = r or recs[0]
    p = r["pred"]
    parsed = Parsed(
        real_incident=p["real_incident"], failure_category=p["failure_category"],
        failure_category_confidence=p.get("category_confidence", 0.0), suspect_component=p.get("suspect_component", ""),
        root_cause=p.get("root_cause", ""), deploy_correlated=p["deploy_correlated"], severity=p["severity"],
        severity_confidence=p.get("severity_confidence", 0.0), blast_radius=p.get("blast_radius", 0.0),
        customer_impact=p.get("customer_impact", 0.0), safe_to_autorollback=p.get("safe_to_autorollback", 0.0),
        proposed_action=p["proposed_action"], proposed_action_confidence=p.get("action_confidence", 0.0),
        action_risk=p.get("action_risk", 0.0), needs_page=p.get("needs_page", 0.0))
    qa = [["Is this a real incident?", f"{p['real_incident']:.2f}"],
          ["Failure category", p["failure_category"]],
          ["Suspected component", p.get("suspect_component", "")],
          ["Likely root cause", p.get("root_cause", "")],
          ["Recent change implicated?", f"{p['deploy_correlated']:.2f}"],
          ["Severity (0-3)", f"{p['severity']:.2f}"],
          ["Blast radius (0-3)", f"{p.get('blast_radius', 0.0):.2f}"],
          ["Customer impact?", f"{p.get('customer_impact', 0.0):.2f}"],
          ["Rollback safe?", f"{p.get('safe_to_autorollback', 0.0):.2f}"],
          ["Proposed first action", p["proposed_action"]],
          ["Action risk (0-2)", f"{p.get('action_risk', 0.0):.2f}"],
          ["Page a person?", f"{p.get('needs_page', 0.0):.2f}"]]
    return {"id": r["incident_id"], "archetype": r["archetype"], "outcome": r["decision"]["outcome"],
            "action": p["proposed_action"], "checks": explain(parsed), "state": r.get("state", ""), "qa": qa}


def table_with_band(slide, spec, y=2.25, avail=5.45):
    rows, headers = spec["rows"], spec["headers"]
    n = len(rows)
    reserve = .9 if spec.get("takeaway") else .15
    row_h = min(.83, (avail - y - reserve) / max(n, 1))
    font = 16 if n <= 4 else (11 if n <= 8 else 9)
    widths = spec.get("widths") or ([3.0, 4.0, 5.15] if len(headers) == 3 else [2.0, 10.1])
    table(slide, headers, rows, x=.6, y=y, widths=widths, row_h=row_h, font=font)
    if spec.get("takeaway"):
        band(slide, spec, min(y + .51 + n * row_h + .12, 5.5))


def build_deck(story, facts, sources, target):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    prs.core_properties.title = "AI in IT operations: the emerging role of a decision model"
    prs.core_properties.subject = "ZeroOps / Jev - CIO discussion edition (v4)"
    prs.core_properties.author = ""
    for index, spec in enumerate(story["slides"], 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        layout = spec["layout"]
        if layout == "cover":
            box(slide, 0, 0, 13.333, 7.5, NAVY)
            text(slide, "IT OPERATIONS  /  CIO DISCUSSION  /  OCTOBER 2026", .9, .72, 12, .3, 12, "8BCCD0", True)
            text(slide, spec["title"], .9, 2.5, 11.4, 1.5, 40, "FFFFFF", True)
            rule(slide, 4.45, .9, 11.5, "527086")
            text(slide, spec["subtitle"], .9, 4.72, 10.4, .8, 18, "C7D6DE")
            slide.notes_slide.notes_text_frame.text = spec.get("notes", "")
            continue
        if layout == "divider":
            box(slide, 0, 0, 13.333, 7.5, NAVY)
            text(slide, spec["title"], .9, 3.15, 11.4, 1.0, 34, "FFFFFF", True)
            text(slide, spec.get("subtitle", ""), .9, 4.3, 10.4, .6, 16, "8BCCD0")
            slide.notes_slide.notes_text_frame.text = spec.get("notes", "")
            continue
        frame(slide, spec)
        if layout == "columns":
            for i, (h, b) in enumerate(spec["items"]):
                x = .6 + i * 4.15
                rule(slide, 2.35, x, 3.72, TEAL)
                text(slide, h, x, 2.6, 3.66, .8, 21, NAVY, True)
                text(slide, b, x, 3.6, 3.65, 2.2, 16)
        elif layout == "table":
            table_with_band(slide, spec)
        elif layout == "split":
            for i, side in enumerate(("left", "right")):
                x = .6 + i * 6.3
                text(slide, spec[side + "_title"], x, 2.4, 5.7, .8, 21, NAVY, True)
                rule(slide, 3.28, x, 5.7, TEAL)
                text(slide, spec[side], x, 3.5, 5.6, 2.7, 17)
        elif layout == "workflow":
            for i, (h, b) in enumerate(spec["stages"]):
                x = .6 + i * 2.48
                box(slide, x, 2.4, 2.22, 1.5, LIGHT)
                text(slide, h, x + .12, 2.62, 2.0, .6, 18, TEAL, True)
                text(slide, b, x + .12, 3.24, 2.0, .58, 14)
                if i < 4:
                    text(slide, "\u2192", x + 2.25, 2.95, .25, .3, 15)
            text(slide, spec["body"], .6, 4.35, 11.9, 1.7, 17)
        elif layout == "metrics":
            for i, (num, label) in enumerate(spec["items"]):
                x = .6 + i * 4.15
                text(slide, num, x, 2.3, 3.7, .85, 42, TEAL, True)
                text(slide, label, x, 3.3, 3.7, 1.0, 16)
            rule(slide, 4.5)
            text(slide, spec["body"], .6, 4.68, 12.05, .8, 16)
            band(slide, spec, 5.55)
        elif layout == "example_one":
            e = network_example()
            text(slide, f'{e["id"]} \u00b7 {e["archetype"].replace("_", " ")} \u00b7 {e["outcome"]}',
                 .6, 2.15, 12, .4, 16, NAVY, True)
            table(slide, ["Check", "Value / rule", "Margin / result"], checks_rows(e),
                  x=.6, y=2.6, widths=[3.2, 2.4, 2.6], row_h=.4, font=12)
            band(slide, spec, 5.2)
        elif layout == "qa":
            e = network_example()
            text(slide, spec["body"], .6, 2.35, 4.5, 4.0, 14)
            table(slide, ["Question", "Answer"], e["qa"], x=5.35, y=2.3, widths=[3.4, 3.9],
                  row_h=.3, font=10)
        elif layout == "example_list":
            for i, key in enumerate(("auto", "stopped")):
                e = facts["jev"]["examples"][key]
                x = .6 + i * 6.3
                text(slide, f'{e["id"]} \u00b7 {e["archetype"].replace("_", " ")} \u00b7 {e["outcome"]}',
                     x, 2.2, 6.0, .38, 15, NAVY, True)
                table(slide, ["Check", "Value / rule", "Margin / result"], checks_rows(e),
                      x=x, y=2.66, widths=[2.3, 1.7, 1.95], row_h=.32, font=10)
            band(slide, spec, 5.5)
        elif layout == "comparison":
            rows = []
            for b in facts["backends"].values():
                rows.append([b["label"], f'{b["action_exact"]["k"]}/{b["n"]}',
                             f'{b["action_acceptable"]["k"]}/{b["n"]}', f'{b["auto"]}/{b["n"]}',
                             f'{b["auto_exact"]}/{b["auto"]}' if b["auto"] else "\u2014",
                             f'{b["p50_ms"]:.0f}/{b["p95_ms"]:.0f}',
                             f'${b["cost_per_1k_usd"]:.3f}' if b["cost_per_1k_usd"] else "GPU uncosted"])
            table(slide, ["Backend", "Exact action", "Acceptable*", "AUTO", "Exact / AUTO", "p50/p95 ms", "API $ / 1k"],
                  rows, y=2.3, widths=[3.1, 1.43, 1.45, 1.05, 1.62, 1.62, 1.96], row_h=.5, font=13)
            text(slide, "*Acceptable-action criteria were defined after the first run; use exact action match as the primary measure.",
                 .6, 4.82, 12.2, .4, 11, GREY)
            band(slide, spec, 5.2)
        elif layout == "integration":
            for i, (h, b) in enumerate(spec["blocks"]):
                x = .6 + i * 4.15
                box(slide, x, 2.35, 3.75, 1.45, TEAL if i == 1 else LIGHT)
                col = "FFFFFF" if i == 1 else NAVY
                text(slide, h, x + .2, 2.55, 3.35, .5, 21, col, True)
                text(slide, b, x + .2, 3.15, 3.35, .6, 15, col)
                if i < 2:
                    text(slide, "\u2192", x + 3.8, 2.85, .35, .4, 22)
            text(slide, "Possible responses within the workflow", .6, 4.0, 11.9, .4, 15, GREY)
            for i, value in enumerate(spec["responses"]):
                text(slide, value, .6 + i * 4.15, 4.45, 3.9, .5, 19, NAVY, True)
            text(slide, spec["body"], .6, 5.1, 11.9, 1.2, 16)
        elif layout == "levers":
            for i, (name, hyp, meas) in enumerate(spec["levers"]):
                x = .6 + i * 3.12
                box(slide, x, 2.3, 2.95, 2.2, LIGHT)
                box(slide, x, 2.3, 2.95, .04, TEAL)
                text(slide, name, x + .14, 2.44, 2.67, .4, 17, NAVY, True)
                text(slide, hyp, x + .14, 2.9, 2.67, .9, 12)
                text(slide, meas, x + .14, 3.82, 2.67, .6, 11, GREY)
            text(slide, spec["body"], .6, 4.75, 12.05, 1.4, 16)
        elif layout == "stages":
            for i, (name, benefit, measure) in enumerate(spec["levers"]):
                x = .6 + i * 3.12
                box(slide, x, 2.12, 2.95, 1.7, LIGHT)
                box(slide, x, 2.12, 2.95, .04, TEAL)
                text(slide, name, x + .14, 2.24, 2.67, .34, 16, NAVY, True)
                text(slide, benefit, x + .14, 2.62, 2.67, .6, 11)
                text(slide, measure, x + .14, 3.24, 2.67, .5, 10, GREY)
            y = 3.96
            for h, b in spec["stages"]:
                box(slide, .6, y, 12.13, .52, "F8FAFB")
                text(slide, h, .78, y + .05, 3.9, .42, 12.5, TEAL, True)
                text(slide, b, 4.7, y + .05, 7.9, .44, 11)
                y += .58
            text(slide, spec["help"], .6, y + .02, 12.1, .48, 11, GREY)
        elif layout == "sources":
            for i, source in enumerate(sources.values()):
                x, y = .6 + (i // 4) * 6.3, 2.35 + (i % 4) * .85
                shp = text(slide, source["id"] + "  " + source["name"], x, y, 5.8, .55, 15, NAVY, True)
                for p in shp.text_frame.paragraphs:
                    for run in p.runs:
                        run.hyperlink.address = source["url"]
                text(slide, "Linked primary source", x, y + .5, 5.7, .24, 9, GREY)
            text(slide, "Example figures: saved facts and the results report; corpus " + facts["corpus_version"],
                 .6, 5.95, 12, .3, 10, GREY)
        footer(slide, spec, index, sources)
        notes = spec["notes"] + "\n\n" + "\n".join(sources[r]["name"] + ": " + sources[r]["url"] for r in spec.get("refs", []))
        slide.notes_slide.notes_text_frame.text = notes
    prs.save(target)


def main():
    existing = [p for d in (paths.CONTENT, paths.SCRIPTS, paths.PACKAGE, paths.TESTS)
                for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    before = {p: digest(p) for p in existing}
    facts = json.loads(paths.FACTS.read_text())
    story = fill(json.loads(loc.STORY.read_text()), context(facts))
    sources = {s["id"]: s for s in json.loads(loc.SOURCES.read_text())}
    build_deck(story, facts, sources, loc.DECK)
    export_pdf(loc.DECK, loc.DECK.parent)          # -> outputs/1_ZeroOps-Jev_v4.pdf
    loc.PREVIEWS.mkdir(parents=True, exist_ok=True)
    for old in loc.PREVIEWS.glob("slide-*.png"):
        old.unlink()
    subprocess.run(["pdftoppm", "-scale-to", "1400", "-png", str(loc.DECK_PDF), str(loc.PREVIEWS / "slide")],
                   check=True, timeout=120)
    changed = [str(p) for p, sha in before.items() if digest(p) != sha]
    if changed:
        raise RuntimeError(f"project files changed: {changed}")
    n = len(list(loc.PREVIEWS.glob("slide-*.png")))
    print(f"Wrote {paths.rel(loc.DECK)}, {paths.rel(loc.DECK_PDF)} and {n} slide images in {paths.rel(loc.PREVIEWS)}/.")


if __name__ == "__main__":
    main()
