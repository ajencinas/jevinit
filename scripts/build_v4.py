#!/usr/bin/env python3
"""Build the v4 discussion edition (single story.json; deck only, no memo).

  ./jev/bin/python scripts/build_v4.py
Writes outputs/v4/ (or outputs/v4/build_NN if a build already exists).
Numbers from work/results/facts.json; the network example is read from the decision log.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zeroops import paths
from zeroops import v4_paths as loc
from zeroops.schema import Parsed
from zeroops.policy import explain
from build_cio_v2 import context, fill, digest, box, text, export_pdf, checks_rows, INK

NAVY, TEAL, GREY, LIGHT, PALE, LINE_GREY = "142E42", "007F82", "596A76", "EFF4F6", "F8FAFB", "CCD7DD"
MUTED, PALE_TEAL = "9AABB5", "8BCCD0"
L, R, W = .6, 12.733, 12.133        # content left edge, right edge and width (inches)
BOTTOM, FOOT = 6.72, 6.9            # content stops at BOTTOM; the footer rule sits at FOOT
GAP = .3                            # between cards
LINE = 1.2                          # line pitch as a multiple of the font size, measured in the exported PDF
INDENT, AFTER = .28, 7              # bullet lists: hanging indent (inches) and space after each item (pt)

# LibreOffice exports the deck with Noto Sans in place of Aptos, so text is measured with it to size the
# boxes; Aptos is narrower, so what fits in the PDF also fits in PowerPoint.
try:
    FONTS = {b: ImageFont.truetype(f"NotoSans-{'Bold' if b else 'Regular'}.ttf", 1000) for b in (False, True)}
except OSError:
    FONTS = {}


SECTION_ICON = {
    "THE INDUSTRY": "network", "THE GAP": "flow", "THE OPPORTUNITY": "target", "AN EXAMPLE": "alert",
    "THE EVIDENCE": "chart", "WHERE IT FITS": "link", "THE VALUE": "gauge", "THE PATH": "path",
    "THE DEMO": "play",
    "Appendix": "spark", "APPENDIX A1": "chart", "APPENDIX A2": "checklist", "APPENDIX A3": "grid",
    "APPENDIX A4": "shield", "APPENDIX A5": "question", "APPENDIX A6": "scale",
    "APPENDIX A7": "info", "SOURCES": "book",
}


def span(value, size, bold=False):
    """Width of one line of text, in inches."""
    if FONTS:
        return FONTS[bold].getlength(value) * size / 1000 / 72
    return len(value) * size * (.6 if bold else .56) / 72


def lines(value, size, width, bold=False):
    n = 0
    for para in value.split("\n"):
        n, line = n + 1, ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and span(trial, size, bold) > width * .99:
                n, line = n + 1, word
            else:
                line = trial
    return n


def height(value, size, width, bold=False):
    """Height of wrapped text, in inches, including the 3 pt after each paragraph that text() adds.
    A list is a bulleted list, as bullets() draws it."""
    if not value:
        return 0
    if isinstance(value, list):
        n = sum(lines(item, size, width - INDENT, bold) for item in value)
        return (n * LINE + .16) * size / 72 + (len(value) - 1) * AFTER / 72
    return (lines(value, size, width, bold) * LINE + .16) * size / 72 + (value.count("\n") + 1) * 3 / 72


def write(slide, value, x, y, w, h, size, color=INK, bold=False, anchor=None, align=None):
    shp = text(slide, value, x, y, w, h, size, color, bold)
    if anchor is not None:
        shp.text_frame.vertical_anchor = anchor
    if align is not None:
        for p in shp.text_frame.paragraphs:
            p.alignment = align
    return shp


def bullets(slide, items, x, y, w, h, size, color=INK, bold=False):
    """One text box, one teal-bulleted paragraph per item, with a hanging indent."""
    shp = write(slide, "\n".join(items), x, y, w, h, size, color, bold)
    for p in shp.text_frame.paragraphs:
        p.space_after = Pt(AFTER)
        ppr = p._p.get_or_add_pPr()
        ppr.set("marL", str(Inches(INDENT)))
        ppr.set("indent", str(-Inches(INDENT)))
        clr, rgb, font, char = (OxmlElement(t) for t in ("a:buClr", "a:srgbClr", "a:buFont", "a:buChar"))
        rgb.set("val", TEAL)
        clr.append(rgb)
        font.set("typeface", "Arial")
        char.set("char", "\u2022")
        for el in (clr, font, char):
            ppr.insert_element_before(el, "a:tabLst", "a:defRPr", "a:extLst")
    return shp


def picture(slide, name, x, y, size):
    slide.shapes.add_picture(str(paths.ICONS / f"{name}.png"), Inches(x), Inches(y), Inches(size), Inches(size))


def link(shape, url):
    for p in shape.text_frame.paragraphs:
        for run in p.runs:
            run.hyperlink.address = url


def rule(slide, y, x=L, w=W, color=LINE_GREY):
    box(slide, x, y, w, .012, color)


def arrow(slide, x, y, w=.2, h=.3, color=TEAL):
    """A small chevron centred on (x, y), pointing right."""
    return box(slide, x - w / 2, y - h / 2, w, h, color, MSO_SHAPE.CHEVRON)


def card(slide, x, y, w, h, color=LIGHT, accent=TEAL):
    box(slide, x, y, w, h, color)
    box(slide, x, y, w, .05, accent)


def cards(slide, items, top, styles, pad=.25, gap=GAP):
    """A row of equal-height cards; styles gives (size, colour, bold) for each field of an item.
    Returns the bottom edge."""
    n = len(items)
    w = (W - gap * (n - 1)) / n
    inner = w - 2 * pad
    heights = [max(height(item[f], size, inner, bold) for item in items)
               for f, (size, _, bold) in enumerate(styles)]
    used = [h for h in heights if h]
    bottom = top + 2 * pad + .05 + sum(used) + .14 * (len(used) - 1)
    for i, item in enumerate(items):
        x = L + i * (w + gap)
        card(slide, x, top, w, bottom - top)
        y = top + pad + .05
        for f, (size, color, bold) in enumerate(styles):
            if heights[f]:
                (bullets if isinstance(item[f], list) else write)(slide, item[f], x + pad, y, inner, heights[f],
                                                                  size, color, bold)
                y += heights[f] + .14
    return bottom


def cell(slide, value, x, y, w, h, color, size, ink=INK, bold=False, pad=.12):
    box(slide, x, y, w, h, color)
    return write(slide, value, x + pad, y, w - 2 * pad, h, size, ink, bold, MSO_ANCHOR.MIDDLE)


def auto_widths(headers, rows, font, width=W, least=.85):
    """Column widths from each column's longest line: scaled down to the width if too wide, otherwise the
    room left over goes to the text columns in proportion (a short code column such as "C10" keeps its width)."""
    natural = [max(least, span(headers[c], 13, True), *(span(str(r[c]), font, c == 0) for r in rows)) + .3
               for c in range(len(headers))]
    if sum(natural) >= width:
        return [n * width / sum(natural) for n in natural]
    wide = sum(n for n in natural if n > 1.5)
    return [n + (width - sum(natural)) * n / wide if n > 1.5 else n for n in natural]


def row_heights(headers, rows, widths, font, least, pad=.16):
    head = max(.42, max(height(h, 13, w - .24, True) for h, w in zip(headers, widths)) + .14)
    body = [max(least, max(height(str(v), font, w - .24, c == 0)
                           for c, (v, w) in enumerate(zip(row, widths))) + pad) for row in rows]
    return head, body


def grid(slide, headers, rows, x, y, widths, font, least=.36, pad=.16):
    """Header row and banded rows; each row is as tall as its longest cell. Returns the bottom edge."""
    head, body = row_heights(headers, rows, widths, font, least, pad)
    offsets = [x]
    for w in widths:
        offsets.append(offsets[-1] + w)
    for c, h in enumerate(headers):
        cell(slide, h, offsets[c], y, widths[c] - .03, head - .03, NAVY, 13, "FFFFFF", True)
    y += head
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell(slide, str(value), offsets[c], y, widths[c] - .03, body[r] - .03,
                 LIGHT if r % 2 == 0 else PALE, font, INK, c == 0)
        y += body[r]
    return y


def frame(slide, spec):
    """Section, title, subtitle and icon. Returns where the slide's content starts."""
    box(slide, 0, 0, 13.333, .08, TEAL)
    write(slide, spec["section"].upper(), L, .34, 10, .22, 10, TEAL, True)
    th = height(spec["title"], 25, 11.1, True)
    write(slide, spec["title"], L, .62, 11.1, th, 25, NAVY, True)
    y = .62 + th
    if spec.get("subtitle"):
        sh = height(spec["subtitle"], 14, 11.1)
        write(slide, spec["subtitle"], L, y + .04, 11.1, sh, 14, GREY)
        y += .04 + sh
    ic = SECTION_ICON.get(spec.get("section", "").strip().upper())
    if ic and (paths.ICONS / f"{ic}.png").exists():
        box(slide, R - .78, .3, .78, .78, LIGHT)
        picture(slide, ic, R - .68, .4, .58)
    return y + .38


def footer(slide, spec, index, sources):
    rule(slide, FOOT)
    write(slide, "For discussion \u00b7 October 2026", L, 7.0, 5, .22, 9, GREY)
    # One text box per link, laid out right to left: LibreOffice recolours links that share a paragraph.
    x = R - .6
    for i, ref in enumerate(reversed(spec.get("refs", []))):
        w = span(ref, 9, True) + .04
        x -= w
        link(write(slide, ref, x, 7.0, w, .22, 9, TEAL, True), sources[ref]["url"])
        w = .16 if i < len(spec["refs"]) - 1 else .6
        x -= w
        write(slide, "\u00b7" if i < len(spec["refs"]) - 1 else "Sources", x, 7.0, w - .06, .22, 9, GREY,
              align=PP_ALIGN.RIGHT if w > .2 else PP_ALIGN.CENTER)
    write(slide, str(index), R - .5, 7.0, .5, .22, 9, GREY, align=PP_ALIGN.RIGHT)


def band_height(spec, w=W):
    if not spec.get("takeaway"):
        return 0
    return height(spec["takeaway"], 14, w - .5, True) + .28 + (.3 if spec.get("source") else 0)


def band(slide, spec, y, x=L, w=W):
    """The navy takeaway band, with its source line underneath. Returns the bottom edge."""
    if not spec.get("takeaway"):
        return y
    h = height(spec["takeaway"], 14, w - .5, True) + .28
    box(slide, x, y, w, h, NAVY)
    write(slide, spec["takeaway"], x + .25, y, w - .5, h, 14, "FFFFFF", True, MSO_ANCHOR.MIDDLE)
    y += h
    if spec.get("source"):
        write(slide, spec["source"], x, y + .08, w, .2, 9, GREY)
        y += .3
    return y


def theme_links(prs, color):
    """Hyperlinks take the theme's link colour (default pure blue); match the deck instead."""
    theme = prs.slide_master.part.part_related_by(RT.THEME)
    for tag in ("hlink", "folHlink"):
        theme._blob = re.sub(rf"<a:{tag}>.*?</a:{tag}>".encode(),
                             f'<a:{tag}><a:srgbClr val="{color}"/></a:{tag}>'.encode(), theme.blob, flags=re.S)


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


def table_with_band(slide, spec, top):
    """The largest font (and roomiest rows) at which the table and its takeaway fit above the footer."""
    rows, headers = spec["rows"], spec["headers"]
    n = len(rows)
    room = BOTTOM - top - (band_height(spec) + .2 if spec.get("takeaway") else 0)
    least = min(.62 if n <= 4 else .52, (room - .45) / n)
    for font in range(15 if n <= 7 else 13, 10, -1):
        widths = spec.get("widths") or auto_widths(headers, rows, font)
        pad = next((p for p in (.16, .12, .08) if sum(row_heights(headers, rows, widths, font, least, p)[1]) + .45
                    <= room), None)
        if pad:
            break
    bottom = grid(slide, headers, rows, L, top, widths, font, least, pad or .08)
    band(slide, spec, bottom + .2)


def build_deck(story, facts, sources, target):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    prs.core_properties.title = "AI in IT operations: the emerging role of a decision model"
    prs.core_properties.subject = "ZeroOps / Jev - CIO discussion edition (v4)"
    prs.core_properties.author = ""
    theme_links(prs, TEAL)
    for index, spec in enumerate(story["slides"], 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        layout = spec["layout"]
        if layout == "cover":
            box(slide, 0, 0, 13.333, 7.5, NAVY)
            box(slide, 0, 0, 13.333, .08, TEAL)
            text(slide, "IT OPERATIONS  /  CIO DISCUSSION  /  OCTOBER 2026", .9, .72, 12, .3, 12, "8BCCD0", True)
            th = height(spec["title"], 40, 11.4, True)
            write(slide, spec["title"], .9, 4.2 - th, 11.4, th, 40, "FFFFFF", True)
            box(slide, .9, 4.45, 1.2, .06, TEAL)
            text(slide, spec["subtitle"], .9, 4.72, 10.4, .8, 20, "C7D6DE")
            slide.notes_slide.notes_text_frame.text = spec.get("notes", "")
            continue
        if layout == "divider":
            box(slide, 0, 0, 13.333, 7.5, NAVY)
            box(slide, 0, 0, 13.333, .08, TEAL)
            write(slide, spec["title"], .9, 3.0, 11.4, .8, 36, "FFFFFF", True, MSO_ANCHOR.BOTTOM)
            box(slide, .9, 3.98, 1.2, .06, TEAL)
            text(slide, spec.get("subtitle", ""), .9, 4.22, 10.4, .6, 18, "8BCCD0")
            slide.notes_slide.notes_text_frame.text = spec.get("notes", "")
            continue
        top = frame(slide, spec)
        if layout == "columns":
            cards(slide, spec["items"], top, [(19, NAVY, True), (16, INK, False)], pad=.25)
        elif layout == "table":
            table_with_band(slide, spec, top)
        elif layout == "split":
            items = [(spec[side + "_title"], spec[side]) for side in ("left", "right")]
            size = 16 if isinstance(items[0][1], list) else 17
            cards(slide, items, top, [(21, NAVY, True), (size, INK, False)], pad=.32, gap=.4)
        elif layout == "before_after":
            # Two cards, each step with its icon, the outcome pinned to the bottom; grey before, teal after.
            sides, gap, pad, ic, badge = (spec["before"], spec["after"]), .7, .3, .3, .66
            w = (W - gap) / 2
            tw, ow = w - 2 * pad - ic - .2, w - 2 * pad - ic - .55
            steps_h = max(sum(max(ic, height(t, 15, tw)) + .14 for _, t in side["steps"]) for side in sides)
            out_h = max(height(side["outcome"][1], 14, ow, True) for side in sides) + .3
            bottom = top + .05 + pad + badge + .3 + steps_h + .12 + out_h + pad
            for i, side in enumerate(sides):
                x, accent = L + i * (w + gap), TEAL if i else MUTED
                card(slide, x, top, w, bottom - top, accent=accent)
                y = top + .05 + pad
                box(slide, x + pad, y, badge, badge, "FFFFFF", MSO_SHAPE.OVAL)
                picture(slide, side["icon"], x + pad + .14, y + .14, badge - .28)
                write(slide, side["title"], x + pad + badge + .22, y, w - 2 * pad - badge - .22, badge, 21, NAVY, True,
                      MSO_ANCHOR.MIDDLE)
                y += badge + .3
                for name, value in side["steps"]:
                    th = height(value, 15, tw)
                    picture(slide, name, x + pad, y + (15 * LINE / 72 - ic) / 2, ic)
                    write(slide, value, x + pad + ic + .2, y, tw, th, 15)
                    y += max(ic, th) + .14
                y = bottom - pad - out_h
                box(slide, x + pad, y, w - 2 * pad, out_h, "FFFFFF")
                box(slide, x + pad, y, .06, out_h, accent)
                picture(slide, side["outcome"][0], x + pad + .22, y + (out_h - ic) / 2, ic)
                write(slide, side["outcome"][1], x + pad + ic + .42, y, ow, out_h, 14, NAVY, True, MSO_ANCHOR.MIDDLE)
            arrow(slide, L + w + gap / 2, (top + bottom) / 2, w=.24, h=.42)
        elif layout == "workflow":
            # The middle stages are where the body says a decision component fits; they are filled teal.
            n, gap = len(spec["stages"]), .4
            w = (W - gap * (n - 1)) / n
            hh = max(height(h, 19, w - .4, True) for h, _ in spec["stages"])
            bh = max(height(b, 15, w - .4) for _, b in spec["stages"])
            bottom = top + .3 + hh + .12 + bh + .3
            for i, (h, b) in enumerate(spec["stages"]):
                x, mid = L + i * (w + gap), 0 < i < n - 1
                box(slide, x, top, w, bottom - top, TEAL if mid else LIGHT)
                write(slide, h, x + .2, top + .3, w - .4, hh, 19, "FFFFFF" if mid else TEAL, True)
                write(slide, b, x + .2, top + .3 + hh + .12, w - .4, bh, 15, "FFFFFF" if mid else INK)
                if i < n - 1:
                    arrow(slide, x + w + gap / 2, (top + bottom) / 2, color=GREY, w=.14, h=.26)
            write(slide, spec["body"], L, bottom + .4, W, height(spec["body"], 18, W), 18)
        elif layout == "metrics":
            for i, (num, label) in enumerate(spec["items"]):
                x = L + i * (W + GAP) / 3
                text(slide, num, x, top, 3.7, .85, 42, TEAL, True)
                text(slide, label, x, top + 1.0, 3.7, 1.0, 16)
            rule(slide, top + 2.2)
            text(slide, spec["body"], L, top + 2.38, W, .8, 16)
            band(slide, spec, top + 3.25)
        elif layout == "example_one":
            e = network_example()
            write(slide, f'{e["id"]} · {e["archetype"].replace("_", " ")} · {e["outcome"]}',
                  L, top, 8, .32, 16, NAVY, True)
            widths = [3.3, 2.3, 2.3]
            y = top + .48
            bottom = grid(slide, ["Check", "Value / rule", "Margin / result"], checks_rows(e),
                          L, y, widths, 13, least=.42)
            x = L + sum(widths) + GAP + .05
            box(slide, x, y, R - x, bottom - y, NAVY)
            box(slide, x, y, .06, bottom - y, TEAL)
            write(slide, spec["takeaway"], x + .35, y, R - x - .65, bottom - y, 17, "FFFFFF", True, MSO_ANCHOR.MIDDLE)
            write(slide, spec.get("source", ""), L, bottom + .1, W, .2, 9, GREY)
        elif layout == "qa":
            e = network_example()
            x = L + 4.55
            write(slide, spec["body"], L, top, 4.15, height(spec["body"], 16, 4.15), 16)
            grid(slide, ["Question", "Answer"], e["qa"], x, top, [3.9, R - x - 3.9], 12, least=.36, pad=.08)
        elif layout == "example_list":
            for i, key in enumerate(("auto", "stopped")):
                e = facts["jev"]["examples"][key]
                x = L + i * (W + .4) / 2
                write(slide, f'{e["id"]} · {e["archetype"].replace("_", " ")} · {e["outcome"]}',
                      x, top, 5.9, .32, 15, NAVY, True)
                grid(slide, ["Check", "Value / rule", "Margin / result"], checks_rows(e),
                     x, top + .46, [2.3, 1.7, 1.93], 11, least=.32)
            band(slide, spec, BOTTOM - band_height(spec))
        elif layout == "comparison":
            rows = []
            for b in facts["backends"].values():
                rows.append([b["label"], f'{b["action_exact"]["k"]}/{b["n"]}',
                             f'{b["action_acceptable"]["k"]}/{b["n"]}', f'{b["auto"]}/{b["n"]}',
                             f'{b["auto_exact"]}/{b["auto"]}' if b["auto"] else "—",
                             f'{b["p50_ms"]:.0f}/{b["p95_ms"]:.0f}',
                             f'${b["cost_per_1k_usd"]:.3f}' if b["cost_per_1k_usd"] else "GPU uncosted"])
            bottom = grid(slide, ["Backend", "Exact action", "Acceptable*", "AUTO", "Exact / AUTO", "p50/p95 ms",
                                  "API $ / 1k"], rows, L, top, [2.9, 1.5, 1.5, 1.1, 1.5, 1.6, 2.033], 15, least=.56)
            write(slide, "*Acceptable-action criteria were defined after the first run; use exact action match as "
                  "the primary measure.", L, bottom + .1, W, .25, 11, GREY)
            band(slide, spec, bottom + .5)
        elif layout == "integration":
            n, gap = len(spec["blocks"]), .55
            w = (W - gap * (n - 1)) / n
            hh = max(height(h, 21, w - .5, True) for h, _ in spec["blocks"])
            bh = max(height(b, 15, w - .5) for _, b in spec["blocks"])
            bottom = top + .28 + hh + .1 + bh + .28
            for i, (h, b) in enumerate(spec["blocks"]):
                x, col = L + i * (w + gap), "FFFFFF" if i == 1 else NAVY
                box(slide, x, top, w, bottom - top, TEAL if i == 1 else LIGHT)
                write(slide, h, x + .25, top + .28, w - .5, hh, 21, col, True)
                write(slide, b, x + .25, top + .28 + hh + .1, w - .5, bh, 15, col)
                if i < n - 1:
                    arrow(slide, x + w + gap / 2, (top + bottom) / 2)
            y = bottom + .35
            write(slide, "Possible responses within the workflow", L, y, W, .26, 13, GREY, True)
            y += .38
            for i, value in enumerate(spec["responses"]):
                x = L + i * (w + gap)
                box(slide, x, y, w, .6, PALE)
                box(slide, x, y, .06, .6, TEAL)
                write(slide, value, x + .25, y, w - .4, .6, 18, NAVY, True, MSO_ANCHOR.MIDDLE)
            y += .6 + .35
            write(slide, spec["body"], L, y, W, height(spec["body"], 16, W), 16)
        elif layout == "levers":
            bottom = cards(slide, spec["levers"], top, [(18, NAVY, True), (15, INK, False), (12, GREY, False)],
                           gap=.25)
            write(slide, spec["body"], L, bottom + .4, W, height(spec["body"], 18, W), 18)
        elif layout == "stages":
            # Numbered steps in sequence: what happens in each, then the decision it ends in.
            steps, gap, pad, dot = spec["steps"], .5, .22, .48
            n = len(steps)
            w = (W - gap * (n - 1)) / n
            does_h = max(height(st["does"], 13.5, w - 2 * pad) for st in steps)
            ask_h = max(height(st["decision"], 14, w - 2 * pad, True) for st in steps)
            mid = top + dot + .16
            low = mid + .05 + pad + does_h + pad - .12
            ends = low + .22 + .2 + .04 + ask_h + .12
            for i, st in enumerate(steps):
                x = L + i * (w + gap)
                box(slide, x, top, dot, dot, TEAL, MSO_SHAPE.OVAL)
                write(slide, str(i + 1), x, top, dot, dot, 18, "FFFFFF", True, MSO_ANCHOR.MIDDLE, PP_ALIGN.CENTER)
                write(slide, st["name"], x + dot + .16, top - .05, w - dot - .16, .34, 19, NAVY, True)
                write(slide, st["weeks"], x + dot + .16, top + .29, w - dot - .16, .22, 12, TEAL, True)
                if i < n - 1:
                    arrow(slide, x + w + gap / 2, top + dot / 2, color=MUTED)
                card(slide, x, mid, w, low - mid)
                bullets(slide, st["does"], x + pad, mid + .05 + pad, w - 2 * pad, does_h, 13.5)
                box(slide, x, low, w, ends - low, NAVY)
                box(slide, x + w / 2 - .18, low, .36, .15, LIGHT, MSO_SHAPE.ISOSCELES_TRIANGLE).rotation = 180
                write(slide, "DECISION", x + pad, low + .22, w - 2 * pad, .2, 10, PALE_TEAL, True)
                write(slide, st["decision"], x + pad, low + .46, w - 2 * pad, ask_h, 14, "FFFFFF", True)
            help_ = spec["help_title"] + ":   " + "  \u00b7  ".join(spec["help"])
            hh = height(help_, 12, W - .5, True)
            box(slide, L, ends + .2, W, hh + .16, PALE)
            box(slide, L, ends + .2, .06, hh + .16, TEAL)
            p = write(slide, spec["help_title"] + ":   ", L + .25, ends + .28, W - .5, hh, 12, NAVY, True) \
                .text_frame.paragraphs[0]
            run = p.add_run()
            run.text = "  \u00b7  ".join(spec["help"])
            run.font.name, run.font.size, run.font.bold = "Aptos", Pt(12), False
            run.font.color.rgb = RGBColor.from_string(GREY)
        elif layout == "video":
            pw = 7.6
            ph, px = pw * 9 / 16, R - pw
            if loc.DEMO_VIDEO.exists():
                slide.shapes.add_movie(str(loc.DEMO_VIDEO), Inches(px), Inches(top), Inches(pw), Inches(ph),
                                       poster_frame_image=str(loc.DEMO_POSTER) if loc.DEMO_POSTER.exists() else None,
                                       mime_type="video/mp4")
            write(slide, spec["body"], L, top, px - L - .4, height(spec["body"], 16, px - L - .4), 16)
            if spec.get("runtime"):
                rule(slide, top + ph - .42, L, px - L - .4, TEAL)
                write(slide, spec["runtime"], L, top + ph - .3, px - L - .4, .3, 11, GREY,
                      anchor=MSO_ANCHOR.BOTTOM)
        elif layout == "sources":
            per_col = 4
            w = (W - .4) / 2
            for i, source in enumerate(sources.values()):
                x, y = L + (i // per_col) * (w + .4), top + (i % per_col) * .9
                box(slide, x, y, w, .76, PALE)
                box(slide, x, y, .62, .76, TEAL)
                write(slide, source["id"], x, y, .62, .76, 15, "FFFFFF", True, MSO_ANCHOR.MIDDLE, PP_ALIGN.CENTER)
                link(write(slide, source["name"], x + .85, y + .13, w - 1.0, .3, 15, NAVY, True), source["url"])
                write(slide, "Linked primary source", x + .85, y + .46, w - 1.0, .2, 10, GREY)
            write(slide, "Example figures: saved facts and the results report; corpus " + facts["corpus_version"],
                  L, top + per_col * .9 + .1, W, .25, 11, GREY)
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
