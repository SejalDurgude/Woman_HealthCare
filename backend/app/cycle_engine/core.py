"""Core logic: prediction, uncertainty, next-best input, explanation, tips, PDF brief.

Nothing here writes user data anywhere. Everything runs in memory.
"""
import io
import os
import datetime
import numpy as np
import pandas as pd
import joblib
from sklearn.isotonic import IsotonicRegression

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "model.joblib")

SYMPTOMS = ["age", "BMI", "cycle_irregular", "cycle_length", "acne", "excess_hair", "weight_gain"]
TESTS = ["LH_FSH_ratio", "AMH", "follicle_count"]
FEATURES = SYMPTOMS + TESTS
BINARY = {"cycle_irregular", "acne", "excess_hair", "weight_gain"}

LABELS = {
    "age": "age", "BMI": "BMI", "cycle_irregular": "cycle regularity",
    "cycle_length": "cycle length", "acne": "acne", "excess_hair": "excess hair growth",
    "weight_gain": "recent weight gain", "LH_FSH_ratio": "LH/FSH hormone blood test",
    "AMH": "AMH hormone blood test", "follicle_count": "ovary ultrasound",
}
# (min, max, default, step) for numeric inputs
SPEC = {
    "age": (15.0, 50.0, 25.0, 1.0), "BMI": (14.0, 45.0, 23.0, 0.5),
    "cycle_length": (20.0, 120.0, 30.0, 1.0), "LH_FSH_ratio": (0.1, 6.0, 1.0, 0.1),
    "AMH": (0.1, 20.0, 4.0, 0.1), "follicle_count": (0.0, 40.0, 10.0, 1.0),
}

# Screening zones on calibrated probability p
LOW_BELOW = 0.30     # p < 0.30  -> Low
HIGH_FROM = 0.70     # p >= 0.70 -> High ; in between -> Moderate = "not sure"


class CalibratedModel:
    """Random-forest pipeline + isotonic calibration (fitted on held-out validation data)."""

    def __init__(self, pipe, iso):
        self.pipe, self.iso = pipe, iso

    def proba(self, X):
        raw = self.pipe.predict_proba(X)[:, 1]
        return np.clip(self.iso.predict(raw), 0.01, 0.99)


def load_bundle(path=MODEL_PATH):
    return joblib.load(path)


def to_frame(inputs):
    row = {f: (np.nan if inputs.get(f) is None else float(inputs[f])) for f in FEATURES}
    return pd.DataFrame([row], columns=FEATURES)


def predict(inputs, bundle):
    p = float(bundle["model"].proba(to_frame(inputs))[0])
    risk = "Low" if p < LOW_BELOW else ("High" if p >= HIGH_FROM else "Moderate")
    return {"probability": p, "confidence": max(p, 1 - p), "risk_level": risk,
            "is_uncertain": risk == "Moderate", "data_source": bundle["data_source"]}


def next_best_input(inputs, bundle):
    """Rank missing features by expected confidence gain.

    For each missing feature we try typical values (quantiles, or yes/no weighted by
    prevalence), re-predict, and average the resulting confidence.
    Gain = expected confidence after - confidence now.
    """
    now = predict(inputs, bundle)["confidence"]
    out = []
    for f in [f for f in FEATURES if inputs.get(f) is None]:
        values, weights = bundle["grid"][f]
        rows = []
        for v in values:
            d = dict(inputs)
            d[f] = v
            rows.append(to_frame(d))
        p = bundle["model"].proba(pd.concat(rows, ignore_index=True))
        expected = float(np.dot(weights, np.maximum(p, 1 - p)))
        kind = "test" if f in TESTS else "question"
        reason = f"Would raise how sure we are from about {now:.0%} to about {expected:.0%}."
        if kind == "test":
            reason += " Not done yet? It is worth asking your doctor about."
        out.append({"feature": f, "label": LABELS[f], "gain": expected - now,
                    "expected_confidence": expected, "kind": kind, "reason": reason})
    return sorted(out, key=lambda r: r["gain"], reverse=True)


def phrase(f, v):
    if f == "cycle_irregular":
        return "Irregular cycles" if v >= 0.5 else "Regular cycles"
    if f in BINARY:
        return cap(LABELS[f]) if v >= 0.5 else "No " + LABELS[f]
    if f in TESTS:
        return {"follicle_count": "Your ovary ultrasound result", "AMH": "Your AMH blood test",
                "LH_FSH_ratio": "Your LH/FSH blood test"}[f]
    return f"{cap(LABELS[f])} ({v:g})"


def explain(inputs, bundle, top=4):
    """Local explanation by occlusion: hide each given input and see how the risk changes."""
    base = predict(inputs, bundle)["probability"]
    items = []
    for f in FEATURES:
        if inputs.get(f) is None:
            continue
        d = dict(inputs)
        d[f] = None
        delta = base - predict(d, bundle)["probability"]
        if abs(delta) >= 0.01:
            items.append({"feature": f, "delta": delta,
                          "text": f"{phrase(f, inputs[f])} {'pushed the estimate up' if delta > 0 else 'pushed the estimate down'}"})
    return sorted(items, key=lambda r: abs(r["delta"]), reverse=True)[:top]


def tips(inputs, result):
    t = []
    if result["risk_level"] == "High":
        t.append("Consider booking a visit with a gynecologist or endocrinologist and bring the brief below.")
    if result["risk_level"] == "Moderate":
        t.append("The result is not clear-cut. A doctor can check hormone levels and do an ultrasound to settle it.")
    if inputs.get("cycle_irregular") == 1 and (inputs.get("cycle_length") or 0) > 45:
        t.append("Cycles longer than about 45 days are worth mentioning to a doctor.")
    if inputs.get("acne") == 1 or inputs.get("excess_hair") == 1:
        t.append("Skin and hair changes have several possible causes. A doctor can check hormone levels.")
    if (inputs.get("BMI") or 0) >= 25 and inputs.get("weight_gain") == 1:
        t.append("You might consider gentle regular movement and balanced meals, and discuss goals with a doctor.")
    t.append("Seek medical care soon for very heavy bleeding, severe pain, no period for 3 months or more, or sudden severe symptoms.")
    return t


def value_text(f, v):
    if v is None:
        return "not provided"
    if f == "cycle_irregular":
        return "Irregular" if v >= 0.5 else "Regular"
    if f in BINARY:
        return "Yes" if v >= 0.5 else "No"
    return f"{v:g}"


def cap(s):
    return s[0].upper() + s[1:]


DISCLAIMER = ("This is a screening aid, not a diagnosis. It cannot confirm or rule out PCOS. "
              "Please discuss any concerns with a qualified doctor.")


def make_pdf(inputs, result, history, factors, suggestion, data_source):
    """One-page doctor-ready brief, built entirely in memory."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=14*mm, bottomMargin=14*mm, title="Screening brief")
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor("#534AB7"), spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, spaceBefore=8, spaceAfter=3)
    b = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13)
    warn = ParagraphStyle("w", parent=b, textColor=colors.HexColor("#A32D2D"), fontName="Helvetica-Bold")
    s = [Paragraph("PCOS screening brief", h),
         Paragraph(f"Date: {datetime.date.today().strftime('%d %b %Y')}", b)]
    if data_source == "synthetic":
        s += [Spacer(1, 4), Paragraph("DEMO MODEL: trained on synthetic data. Not for real screening.", warn)]
    s += [Paragraph("Screening result", h2),
          Paragraph(f"Risk level: <b>{result['risk_level']}</b> | Estimated probability: {result['probability']:.0%} | "
                    f"Confidence: {result['confidence']:.0%}", b)]
    if result["is_uncertain"]:
        s.append(Paragraph("The model is not sure about this result.", b))
    if len(history) > 1:
        s.append(Paragraph("Confidence as inputs were added: " + " to ".join(f"{c:.0%}" for _, c in history), b))
    rows = [["Input", "Value"]] + [[cap(LABELS[f]), value_text(f, inputs.get(f))] for f in FEATURES]
    t = Table(rows, colWidths=[85*mm, 60*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEDFE")),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B4B2A9")),
                           ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    s += [Paragraph("Inputs provided", h2), t]
    if factors:
        s.append(Paragraph("What influenced the result", h2))
        s += [Paragraph("- " + f["text"], b) for f in factors]
    s.append(Paragraph("Questions to ask the doctor", h2))
    qs = ["Which tests would help clarify this result (for example hormone levels and a pelvic ultrasound)?",
          "Could anything else explain my symptoms?"]
    if suggestion:
        qs.insert(0, f"Could my {suggestion['label']} be checked? It was the most informative missing input.")
    s += [Paragraph("- " + q, b) for q in qs]
    s += [Paragraph("Disclaimer", h2), Paragraph(DISCLAIMER, b),
          Paragraph("No personal identifiers are stored by this tool.", b)]
    doc.build(s)
    return buf.getvalue()
