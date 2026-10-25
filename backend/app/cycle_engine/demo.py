"""Deterministic demo profiles so judges can see the product working in one click.

Everything here is fabricated for demonstration. No real person's data.
"""
import datetime as dt
import random

SCENARIOS = {
    "irregular": {
        "title": "Irregular cycles, cause unclear",
        "blurb": "Long, unpredictable cycles and some acne. The result is borderline, and the app tells you which test would settle it.",
        "profile": {"age": 24, "height_cm": 162, "weight_kg": 68, "acne": 1, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False},
        "cycles": [41, 47, 39, 52, 44, 38], "dur": (4, 5), "pain": (1, 2), "luteal_drop": 0.3,
        "tags": {"acne": 0.30, "fatigue": 0.10, "bloating": 0.08},
    },
    "pcos": {
        "title": "Classic PCOS-type pattern",
        "blurb": "Long cycles, extra hair, acne and weight gain. Two of the three PCOS signs show up from the log alone.",
        "profile": {"age": 26, "height_cm": 160, "weight_kg": 74, "acne": 1, "excess_hair": 1, "weight_gain": 1,
                    "family_history": [], "hormonal_contraception": False},
        "cycles": [46, 58, 40, 63, 49, 44], "dur": (4, 6), "pain": (1, 3), "luteal_drop": 0.4,
        "tags": {"acne": 0.45, "hair_growth": 0.30, "fatigue": 0.18, "hair_loss": 0.04, "low_mood": 0.12},
    },
    "endo": {
        "title": "Severe cyclical pain",
        "blurb": "Regular cycles but disabling pain, pain during sex and bowel symptoms. The kind of story that takes years to be believed.",
        "profile": {"age": 29, "height_cm": 165, "weight_kg": 58, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": ["endometriosis"], "hormonal_contraception": False},
        "cycles": [28, 29, 27, 28, 30, 28], "dur": (5, 6), "pain": (6, 9), "luteal_drop": 1.3,
        "tags": {"cramps": 0.5, "pain_sex": 0.03, "pain_bowel": 0.4, "bloating": 0.25, "fatigue": 0.25, "nausea": 0.15,
                 "mood_swings": 0.15},
        "pain_off": 0.12,
    },
    "heavy": {
        "title": "Heavy periods and tiredness",
        "blurb": "Long, heavy periods with clots and growing fatigue: a classic route to unnoticed iron deficiency.",
        "profile": {"age": 33, "height_cm": 158, "weight_kg": 61, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False},
        "cycles": [26, 25, 27, 24, 26, 25], "dur": (8, 10), "pain": (3, 5), "luteal_drop": 0.5, "heavy": True,
        "tags": {"clots": 0.6, "flooding": 0.15, "fatigue": 0.5, "dizziness": 0.15, "hair_loss": 0.15, "cold": 0.15},
    },
    "typical": {
        "title": "Typical healthy cycle",
        "blurb": "Regular 28-day cycles and mild symptoms. The app stays calm when nothing is wrong.",
        "profile": {"age": 27, "height_cm": 167, "weight_kg": 60, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False},
        "cycles": [28, 29, 28, 27, 29, 28], "dur": (4, 5), "pain": (1, 3), "luteal_drop": 0.2,
        "tags": {"cramps": 0.2, "bloating": 0.1},
    },
    "peri": {
        "title": "Perimenopause, mid-40s",
        "blurb": "Cycles that jump around, a 2-month gap, hot flushes and broken sleep. Often put down to stress for years.",
        "profile": {"age": 47, "height_cm": 158, "weight_kg": 64, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False, "life_stage": "midlife"},
        "cycles": [27, 36, 24, 43, 29, 66], "dur": (3, 5), "pain": (0, 2), "luteal_drop": 0.5,
        "tags": {"hot_flash": 0.22, "night_sweats": 0.18, "poor_sleep": 0.35, "brain_fog": 0.12, "joint_pain": 0.12,
                 "mood_swings": 0.12, "fatigue": 0.15},
    },
    "anaemia": {
        "title": "Anaemia, low iron",
        "blurb": "Heavy periods, a vegetarian diet and constant tiredness. A blood count of 9.6 g/dL confirms what the log suggested.",
        "profile": {"age": 31, "height_cm": 156, "weight_kg": 55, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False, "life_stage": "reproductive",
                    "hemoglobin": 9.6, "diet": "veg"},
        "cycles": [27, 26, 28, 26, 27, 25], "dur": (7, 9), "pain": (2, 4), "luteal_drop": 0.4, "heavy": True,
        "tags": {"clots": 0.5, "fatigue": 0.55, "dizziness": 0.2, "breathless": 0.2, "brittle_nails": 0.12,
                 "hair_loss": 0.15, "pale": 0.1},
    },
    "postpartum": {
        "title": "Postpartum, low mood",
        "blurb": "Four months after birth: low mood, anxiety and poor sleep on most days. The app flags it kindly and points to help.",
        "profile": {"age": 28, "height_cm": 161, "weight_kg": 63, "acne": 0, "excess_hair": 0, "weight_gain": 0,
                    "family_history": [], "hormonal_contraception": False, "life_stage": "postpartum", "hemoglobin": 10.8},
        "cycles": [31, 33, 30, 34, 32, 31], "dur": (4, 6), "pain": (1, 3), "luteal_drop": 0.6,
        "tags": {"low_mood": 0.45, "anhedonia": 0.3, "anxiety": 0.35, "poor_sleep": 0.5, "fatigue": 0.45},
    },
}


def build(name, today=None, seed=7):
    sc = SCENARIOS[name]
    rng = random.Random(f"{name}-{seed}")
    today = today or dt.date.today()
    total = sum(sc["cycles"])
    start = today - dt.timedelta(days=total + 9)       # last period began about 10 days ago
    logs, day = [], start
    for L in sc["cycles"] + [60]:
        dur = rng.randint(*sc["dur"])
        for i in range(L):
            if day > today:
                break
            dd = day + dt.timedelta(days=i)
            if dd > today:
                break
            bleeding = i < dur
            if bleeding:
                shape = [3, 4, 3, 2, 2, 2, 2, 2, 1, 1]
                flow = shape[min(i, len(shape) - 1)]
                if sc.get("heavy") and i < 5:
                    flow = 4
            else:
                flow = 1 if rng.random() < 0.02 else 0
            pain = rng.randint(*sc["pain"]) if bleeding and i < 3 else rng.randint(0, 2) if bleeding else \
                (rng.randint(4, 6) if rng.random() < sc.get("pain_off", 0) else rng.randint(0, 1))
            lut = i >= L - 7
            base = 4 if not sc["luteal_drop"] else 4
            mood = max(1, min(5, round(base - (sc["luteal_drop"] if lut else 0) + rng.uniform(-0.6, 0.6))))
            energy = max(1, min(5, round(3.6 - (1.2 if sc["tags"].get("fatigue", 0) > 0.4 else 0) + rng.uniform(-1, 1))))
            tags = []
            for t, p in sc["tags"].items():
                pp = p
                if t in ("clots", "flooding"):
                    pp = p if bleeding and i < 5 else 0
                elif t in ("cramps", "pain_bowel"):
                    pp = p if bleeding else 0
                elif t == "pain_sex":
                    pp = p
                elif t in ("mood_swings",) and lut:
                    pp = p * 2.5
                if rng.random() < pp:
                    tags.append(t)
            if rng.random() > 0.06 or bleeding:        # a few missed days, like real life
                logs.append({"date": dd.isoformat(), "flow": flow, "pain": pain, "mood": mood, "energy": energy, "tags": tags})
        day += dt.timedelta(days=L)
    return {"profile": dict(sc["profile"]), "logs": logs}
