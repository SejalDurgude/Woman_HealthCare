"""Clinician brief: a 2-page PDF built in memory from the analysis. Nothing is written to disk."""
import io
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Line, String, Rect
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

import core
import modules

INK, ROSE, TEAL, AMBER = "#1D1530", "#C2255C", "#0F766E", "#B7791F"
LEVEL_TXT = {"elevated": "Strong pattern", "watch": "Worth discussing", "low": "Nothing notable", "insufficient": "Need more data"}
LEVEL_COL = {"elevated": ROSE, "watch": AMBER, "low": TEAL, "insufficient": "#6B6478"}
STATUS_TXT = {"met": "Present", "not_met": "Not seen", "unknown": "Not checked", "possible": "Maybe"}


def _styles():
    b = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12.5, textColor=colors.HexColor(INK))
    return {
        "b": b,
        "small": ParagraphStyle("s", parent=b, fontSize=7.5, leading=10, textColor=colors.HexColor("#6B6478")),
        "h1": ParagraphStyle("h1", parent=b, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor(ROSE)),
        "h2": ParagraphStyle("h2", parent=b, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=9, spaceAfter=3),
        "warn": ParagraphStyle("w", parent=b, fontName="Helvetica-Bold", textColor=colors.HexColor("#A32D2D")),
        "cell": ParagraphStyle("c", parent=b, fontSize=8.5, leading=11),
    }


def _cycle_chart(lengths):
    dr = Drawing(170 * mm, 52 * mm)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 28, 16, 155 * mm / 1.0 - 20, 34 * mm
    ch.data = [lengths]
    ch.categoryAxis.categoryNames = [f"C{i + 1}" for i in range(len(lengths))]
    ch.categoryAxis.labels.fontSize = 7
    ch.valueAxis.valueMin, ch.valueAxis.valueMax = 0, max(60, max(lengths) + 8)
    ch.valueAxis.valueStep = 10
    ch.valueAxis.labels.fontSize = 7
    ch.bars[0].fillColor = colors.HexColor(ROSE)
    ch.barLabelFormat = "%d"
    ch.barLabels.fontSize = 7
    ch.barLabels.nudge = 6
    dr.add(ch)
    # normal band 24-38 days, drawn as two guide lines
    top = ch.y + ch.height
    for v in (24, 38):
        y = ch.y + ch.height * v / ch.valueAxis.valueMax
        dr.add(Line(ch.x, y, ch.x + ch.width, y, strokeColor=colors.HexColor(TEAL), strokeWidth=0.8, strokeDashArray=[3, 2]))
    dr.add(String(ch.x + ch.width - 2, ch.y + ch.height * 38 / ch.valueAxis.valueMax + 2, "normal range 24-38 days",
                  fontSize=6.5, fillColor=colors.HexColor(TEAL), textAnchor="end"))
    dr.add(String(ch.x, top + 6, "Cycle length in days (dashed lines: normal range)", fontSize=7.5, fillColor=colors.HexColor("#6B6478")))
    return dr


def _fp_chart(fp, key, color, title, vmax):
    vals = [(r[key] or 0) for r in fp[:35]]
    dr = Drawing(82 * mm, 42 * mm)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 18, 14, 82 * mm - 26, 24 * mm
    ch.data = [vals]
    ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, vmax, vmax / 2
    ch.valueAxis.labels.fontSize = 6.5
    ch.categoryAxis.categoryNames = [str(i + 1) if (i + 1) % 7 == 0 or i == 0 else "" for i in range(35)]
    ch.categoryAxis.labels.fontSize = 6.5
    ch.bars[0].fillColor = colors.HexColor(color)
    ch.barSpacing = 0
    ch.groupSpacing = 0.5
    dr.add(ch)
    dr.add(String(0, 42 * mm - 8, title, fontSize=7.5, fillColor=colors.HexColor("#6B6478")))
    return dr


def build(profile, analysis, name=None):
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=13 * mm,
                            bottomMargin=13 * mm, title="CycleLens clinical brief")
    cs, ev = analysis["cycle"], analysis["evidence"]
    s = [Paragraph("CycleLens clinical brief", st["h1"]),
         Paragraph(f"Prepared {dt.date.today():%d %b %Y} from " + ("a self-reported questionnaire" if ev["logged_days"] == 0 else
                   f"{ev['logged_days']} days of self-logged data ({ev['cycles']} complete cycles)") + f". Age {profile.get('age') or 'not given'}"
                   + (f", BMI {analysis['profile_bmi']}" if analysis["profile_bmi"] else "")
                   + (f", {modules.STAGE_TXT[profile['life_stage']].lower()}" if profile.get("life_stage") else "")
                   + (f", haemoglobin {profile['hemoglobin']:g} g/dL" if profile.get("hemoglobin") else "")
                   + (". On hormonal contraception." if cs.get("contraception") else "."), st["b"])]
    if analysis["data_source"] == "synthetic":
        s += [Spacer(1, 3), Paragraph("The PCOS probability comes from a research-stage model that has not been validated on clinical data. "
                                      "Treat it as a prompt for discussion, not a result. "
                                      "Rule-based findings below are computed from the answers and logs provided.", st["warn"])]
    if analysis["red_flags"]:
        s += [Paragraph("Urgent flags", st["h2"])] + [Paragraph("! " + r, st["warn"]) for r in analysis["red_flags"]]

    # cycle summary
    s.append(Paragraph("Cycle summary", st["h2"]))
    if cs.get("n_cycles", 0) >= 1:
        rows = [["Mean cycle", f"{cs['mean']} days", "Shortest / longest", f"{cs['shortest']} / {cs['longest']} days"],
                ["Spread", f"{cs['spread']} days", "Mean period length", f"{sum(cs['durations']) / len(cs['durations']):.1f} days"],
                ["Last period began", cs["last_start"], "Current cycle day", str(cs.get("cycle_day", "not shown (no recent log)"))]]
        t = Table(rows, colWidths=[38 * mm, 40 * mm, 40 * mm, 56 * mm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                               ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8D3E0")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        s += [t] + [Paragraph("- " + l, st["b"]) for l in cs["labels"]]
        s.append(_cycle_chart(cs["lengths"]))
    elif cs.get("labels"):
        s += [Paragraph("- " + l, st["b"]) for l in cs["labels"]]
    else:
        s.append(Paragraph("Not enough bleeding days logged to calculate cycle lengths.", st["b"]))

    # conditions
    s.append(Paragraph("Patterns found", st["h2"]))
    rows = [[Paragraph("<b>Pattern</b>", st["cell"]), Paragraph("<b>Signal</b>", st["cell"]), Paragraph("<b>Evidence</b>", st["cell"])]]
    for c in analysis["conditions"]:
        if c["id"] == "pcos":
            evt = "<br/>".join(f"{STATUS_TXT[k['status']]}: {k['name']} ({k['detail']})" for k in c["rotterdam"]["criteria"])
        else:
            evt = "<br/>".join(f"{e['points']:+d} {e['text']}" for e in c["evidence"]) or "No supporting evidence in the log."
        rows.append([Paragraph(c["name"], st["cell"]),
                     Paragraph(f"<font color='{LEVEL_COL[c['level']]}'><b>{LEVEL_TXT[c['level']]}</b></font>", st["cell"]),
                     Paragraph(evt, st["cell"])])
    t = Table(rows, colWidths=[38 * mm, 28 * mm, 108 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1ECF6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CFC8DA")),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    s.append(t)
    pc = analysis["conditions"][0]
    if pc.get("ml"):
        r = pc["ml"]["result"]
        s.append(Paragraph(f"PCOS model estimate: {r['probability']:.0%} probability, {r['confidence']:.0%} confidence"
                           + (" (the model is not sure)." if r["is_uncertain"] else "."), st["small"]))

    # fingerprint
    fp = analysis["fingerprint"]
    if any(r["pain"] is not None for r in fp):
        s.append(Paragraph("Cycle fingerprint (average by cycle day)", st["h2"]))
        t = Table([[_fp_chart(fp, "pain", ROSE, "Pain 0-10", 10), _fp_chart(fp, "mood", TEAL, "Mood 1-5 (5 is best)", 5)]],
                  colWidths=[87 * mm, 87 * mm])
        s.append(KeepTogether(t))
    if analysis["symptom_counts"]:
        s.append(Paragraph("Most logged symptoms: " + ", ".join(f"{x['label']} ({x['days']} days)" for x in analysis["symptom_counts"][:6]) + ".", st["b"]))

    # questions
    s.append(Paragraph("Suggested questions and tests to raise", st["h2"]))
    qs = []
    for n in analysis["next_steps"]:
        if n["kind"] == "test":
            qs.append(f"Could we check: {n['title'].lower()}? ({n['why']})")
    for c in analysis["conditions"]:
        if c["level"] in ("watch", "elevated"):
            qs += [f"[{c['name']}] {q}" for q in c["discuss"][:2]]
    qs.append("Could anything else explain these symptoms, and what would you like me to keep tracking?")
    s += [Paragraph("- " + q, st["b"]) for q in qs[:9]]

    s += [Spacer(1, 4), Paragraph("Disclaimer", st["h2"]), Paragraph(core.DISCLAIMER, st["b"]),
          Paragraph("Data was kept on the patient's device and analysed in memory. No name or identifier appears in this document.", st["small"])]
    doc.build(s)
    return buf.getvalue()
