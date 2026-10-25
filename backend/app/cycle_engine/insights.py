"""CycleLens insight engine: turns a few months of daily logs into explainable clinical signals.

Design rules
- Every signal is transparent: points + the evidence behind them. No black box except the PCOS
  probability, which is labelled with its data source (synthetic in the demo build).
- Thresholds follow published frameworks: FIGO 2018 AUB system (cycle frequency / regularity /
  duration), the 2023 international PCOS guideline / Rotterdam criteria, and common clinical red
  flags for endometriosis, heavy menstrual bleeding and thyroid disease.
- This is a screening aid. It never diagnoses.
"""
import datetime as dt
from statistics import mean, pstdev

import core
import modules

TAGS = {
    "cramps": "Cramps", "bloating": "Bloating", "acne": "Acne", "hair_growth": "Excess hair growth",
    "hair_loss": "Hair loss", "fatigue": "Fatigue", "headache": "Headache", "nausea": "Nausea",
    "clots": "Large clots", "flooding": "Soaking a pad/tampon in under 1 hour",
    "pain_sex": "Pain during sex", "pain_bowel": "Painful bowel movement",
    "pain_urination": "Painful urination", "cold": "Feeling unusually cold",
    "palpitations": "Racing heart", "mood_swings": "Mood swings", "anxiety": "Anxiety",
    "low_mood": "Low mood", "spotting": "Spotting between periods", "dizziness": "Dizziness",
    "fainting": "Fainting", "severe_pain": "Sudden severe pain",
}
TAGS.update(modules.NEW_TAGS)
RED_TAGS = {"fainting", "severe_pain", "flooding"}     # life-stage danger signs are handled in modules.red_flags

LEVELS = ("insufficient", "low", "watch", "elevated")
STALE_AFTER_DAYS = 14        # no log for this long: do not trust "days since last period"


def d(s):
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------- cycles
def find_periods(logs):
    """Bleeding episodes: days with flow >= 2 (light or more), gaps over 7 days start a new one."""
    days = sorted((d(l["date"]), l) for l in logs if (l.get("flow") or 0) >= 2)
    eps = []
    for day, l in days:
        if eps and (day - eps[-1]["end"]).days <= 7:
            eps[-1]["end"] = day
            eps[-1]["flows"].append(l["flow"])
        else:
            eps.append({"start": day, "end": day, "flows": [l["flow"]]})
    for e in eps:
        e["duration"] = (e["end"] - e["start"]).days + 1
        e["heavy_days"] = sum(1 for f in e["flows"] if f >= 4)
    return eps


def cycle_stats(periods, today):
    starts = [p["start"] for p in periods]
    lengths = [(b - a).days for a, b in zip(starts, starts[1:])]
    lengths = [x for x in lengths if 10 <= x <= 200]
    out = {"n_periods": len(periods), "n_cycles": len(lengths), "lengths": lengths,
           "starts": [s.isoformat() for s in starts], "durations": [p["duration"] for p in periods]}
    if not periods:
        return out
    last = starts[-1]
    out["last_start"] = last.isoformat()
    out["cycle_day"] = (today - last).days + 1
    if lengths:
        recent = lengths[-4:]
        out.update(mean=round(mean(lengths), 1), sd=round(pstdev(lengths), 1) if len(lengths) > 1 else 0.0,
                   shortest=min(lengths), longest=max(lengths), spread=max(lengths) - min(lengths))
        pred = last + dt.timedelta(days=round(mean(recent)))
        out["predicted_next"] = pred.isoformat()
        out["predicted_window_days"] = max(2, round(pstdev(recent))) if len(recent) > 1 else 3
        out["days_to_next"] = (pred - today).days
    return out


def figo_labels(cs, age):
    """Describe frequency / regularity / duration using FIGO 2018 normal limits."""
    L = []
    if cs.get("n_cycles", 0) >= 2:
        m = cs["mean"]
        if m < 24:
            L.append("Your periods come more often than usual (under 24 days apart on average)")
        elif m > 38:
            L.append("Your periods come further apart than usual (over 38 days on average)")
        else:
            L.append("Your cycle length is in the normal range (24 to 38 days)")
        limit = 9 if (age and (age <= 25 or age >= 42)) else 7
        L.append(f"Your cycle length changes by up to {cs['spread']} days from one cycle to the next " +
                 (f"(usually under {limit}, so this is less regular than typical)" if cs["spread"] > limit else f"(under {limit} is considered regular)"))
    if cs.get("durations"):
        md = mean(cs["durations"])
        L.append("Your periods last longer than 8 days on average" if md > 8 else f"Your periods last about {md:.0f} days (up to 8 is normal)")
    return L


# ---------------------------------------------------------------- helpers
def tag_days(logs, tag):
    return sum(1 for l in logs if tag in (l.get("tags") or []))


def cond(id_, name, score, maxs, evidence, thresholds, n_logs, min_logs=14, **extra):
    """thresholds = (watch_at, elevated_at)."""
    if n_logs < min_logs:
        level = "insufficient"
    elif score >= thresholds[1]:
        level = "elevated"
    elif score >= thresholds[0]:
        level = "watch"
    else:
        level = "low"
    return {"id": id_, "name": name, "level": level, "score": score, "max_score": maxs,
            "evidence": evidence, **extra}


def pts(evidence, text, p):
    evidence.append({"text": text, "points": p})
    return p


# ---------------------------------------------------------------- conditions
def endometriosis(logs, periods, profile):
    ev, s = [], 0
    bleed = {d(l["date"]) for l in logs if (l.get("flow") or 0) >= 1}
    pain_b = [l["pain"] for l in logs if d(l["date"]) in bleed and l.get("pain") is not None]
    non = [l for l in logs if d(l["date"]) not in bleed and l.get("pain") is not None]
    if pain_b:
        m = mean(pain_b)
        if m >= 6:
            s += pts(ev, f"Severe period pain: average {m:.1f}/10 on bleeding days", 2)
        elif m >= 4:
            s += pts(ev, f"Moderate period pain: average {m:.1f}/10 on bleeding days", 1)
    if non:
        frac = sum(1 for l in non if l["pain"] >= 4) / len(non)
        if frac >= 0.10:
            s += pts(ev, f"Pain of 4/10 or more on {frac:.0%} of non-bleeding days (pelvic pain outside periods)", 2)
    if tag_days(logs, "pain_sex"):
        s += pts(ev, f"Pain during sex logged {tag_days(logs, 'pain_sex')} time(s)", 2)
    cyc = [l for l in logs if d(l["date"]) in bleed and ({"pain_bowel", "pain_urination"} & set(l.get("tags") or []))]
    if cyc:
        s += pts(ev, f"Painful bowel or urinary symptoms during bleeding on {len(cyc)} day(s)", 2)
    if "endometriosis" in (profile.get("family_history") or []):
        s += pts(ev, "Family history of endometriosis", 1)
    return cond("endometriosis", "Endometriosis", s, 9, ev, (3, 5), len(logs),
                discuss=["Ask for a pelvic exam and an ultrasound by a sonographer experienced in endometriosis. A normal scan does not rule it out.",
                         "Ask whether MRI or specialist referral is appropriate if pain persists.",
                         "Bring your pain-by-cycle-day chart: it shows the pattern doctors look for."],
                missing=["Log pain every day, including days with no bleeding",
                         "Tag pain during sex, bowel movements and urination when they happen"],
                note="Average diagnosis delay is several years. A dated pain log is one of the strongest pieces of evidence you can bring.")


def heavy_bleeding(logs, periods, profile):
    ev, s = [], 0
    if periods:
        long_ = [p for p in periods if p["duration"] > 8]
        if long_:
            s += pts(ev, f"{len(long_)} of {len(periods)} periods lasted over 8 days", 2)
        hv = [p for p in periods if p["heavy_days"] >= 3]
        if hv:
            s += pts(ev, f"{len(hv)} of {len(periods)} periods had 3 or more heavy-flow days", 2)
    if tag_days(logs, "flooding"):
        s += pts(ev, f"Soaking through protection within an hour logged {tag_days(logs, 'flooding')} time(s)", 2)
    if tag_days(logs, "clots"):
        s += pts(ev, f"Large clots logged on {tag_days(logs, 'clots')} day(s)", 1)
    if tag_days(logs, "fatigue") >= 5 and (tag_days(logs, "dizziness") or periods and any(p["heavy_days"] for p in periods)):
        s += pts(ev, "Fatigue alongside heavy bleeding can signal iron deficiency", 1)
    if tag_days(logs, "dizziness") >= 2:
        s += pts(ev, f"Dizziness logged on {tag_days(logs, 'dizziness')} days", 1)
    return cond("heavy_bleeding", "Heavy periods and low iron", s, 9, ev, (2, 4), len(logs),
                discuss=["Ask for a blood count (CBC) and ferritin test to check for anaemia and low iron.",
                         "Ask about an ultrasound to look for fibroids or polyps, and about a thyroid test.",
                         "Mention how many pads or tampons you use on the heaviest days."],
                missing=["Rate flow every bleeding day (spotting to heavy)", "Tag clots and flooding when they happen"],
                note="Heavy bleeding is common and treatable, but it often goes unchecked until anaemia develops.")


def thyroid(logs, cs, profile):
    ev, s = [], 0
    n = max(len(logs), 1)
    if tag_days(logs, "fatigue") / n >= 0.25:
        s += pts(ev, f"Fatigue on {tag_days(logs, 'fatigue') / n:.0%} of logged days", 1)
    for t, txt in (("hair_loss", "Hair loss"), ("cold", "Feeling unusually cold"), ("palpitations", "Racing heart")):
        if tag_days(logs, t) >= 3:
            s += pts(ev, f"{txt} on {tag_days(logs, t)} days", 1)
    if profile.get("weight_gain") == 1:
        s += pts(ev, "Recent unexplained weight gain", 1)
    if tag_days(logs, "low_mood") / n >= 0.2:
        s += pts(ev, "Low mood on many days", 1)
    if cs.get("n_cycles", 0) >= 3 and (cs.get("spread", 0) > 9 or cs.get("mean", 30) > 38):
        s += pts(ev, "Irregular cycles (thyroid problems can cause this)", 1)
    if "thyroid" in (profile.get("family_history") or []):
        s += pts(ev, "Family history of thyroid disease", 2)
    return cond("thyroid", "Thyroid health", s, 9, ev, (3, 5), len(logs),
                discuss=["Ask for a TSH blood test (and free T4 if TSH is abnormal). It is cheap and widely available.",
                         "Mention hair, energy, temperature and heart-rate changes together, not one by one."],
                missing=["Tag fatigue, hair loss, feeling cold and racing heart when they happen"],
                note="These symptoms are non-specific and overlap with many causes. A single blood test settles most of the doubt.")


def premenstrual(logs, periods):
    """Compare mood in the 7 days before each period with a mid-cycle baseline."""
    mood = {d(l["date"]): l["mood"] for l in logs if l.get("mood") is not None}
    drops, ev, s = [], [], 0
    starts = [p["start"] for p in periods]
    for a, b in zip(starts, starts[1:]):
        lut = [mood[x] for x in (b - dt.timedelta(days=i) for i in range(1, 8)) if x in mood]
        base = [mood[x] for x in (a + dt.timedelta(days=i) for i in range(5, 13)) if x in mood]
        if len(lut) >= 4 and len(base) >= 4:
            drops.append(mean(base) - mean(lut))
    big = [x for x in drops if x >= 1.0]
    if len(drops) >= 2:
        if len(big) >= 2:
            s += pts(ev, f"Mood dropped by 1 point or more in the week before {len(big)} of {len(drops)} periods", 3)
        elif big:
            s += pts(ev, f"Mood dropped before 1 of {len(drops)} periods", 1)
    pre = {x for p in starts for x in (p - dt.timedelta(days=i) for i in range(1, 8))}
    pm = [l for l in logs if d(l["date"]) in pre and ({"mood_swings", "anxiety", "low_mood"} & set(l.get("tags") or []))]
    if len(pm) >= 4:
        s += pts(ev, f"Mood swings, anxiety or low mood on {len(pm)} premenstrual days", 1)
    return cond("pmdd", "Mood changes before periods", s, 4, ev, (1, 3), len(logs), min_logs=30,
                discuss=["Share your mood-by-cycle-day chart. Doctors need ratings across at least 2 cycles to assess PMDD, and you already have them.",
                         "Ask about options: lifestyle changes, therapy, or medication if it disrupts daily life."],
                missing=["Rate mood daily across at least 2 full cycles"],
                note="Diagnosing PMDD requires prospective daily ratings over two cycles. This log is that evidence.")


# ---------------------------------------------------------------- PCOS
def test_values(p):
    """Model inputs for the three optional tests. Users pick plain answers (scan result, hormone test
    high/normal); we translate them to representative values for the model."""
    v = {k: p.get(k) for k in core.TESTS}
    if v["follicle_count"] is None and p.get("scan") in ("polycystic", "normal"):
        v["follicle_count"] = 24.0 if p["scan"] == "polycystic" else 9.0
    if v["AMH"] is None and p.get("amh_level") in ("high", "normal"):
        v["AMH"] = 7.5 if p["amh_level"] == "high" else 3.0
    if v["LH_FSH_ratio"] is None and p.get("lh_level") in ("high", "normal"):
        v["LH_FSH_ratio"] = 2.2 if p["lh_level"] == "high" else 1.0
    return v


def effective_flag(profile, key, logs, tag):
    v = profile.get(key)
    if v is not None:
        return int(v)
    if len(logs) >= 14:
        return 1 if tag_days(logs, tag) >= 3 else 0
    return None


def rotterdam(profile, cs, logs, today, ov_override=None):
    """Three signs; two of three (after a doctor rules out other causes) point towards PCOS."""
    contra = bool(profile.get("hormonal_contraception"))
    lengths = cs.get("lengths", [])
    since = cs.get("cycle_day", 0)
    if ov_override is not None:
        ov = ov_override
    elif contra:
        ov = ("unknown", "Hormonal contraception hides your natural cycle, so this cannot be judged")
    elif len(lengths) >= 3:
        long_share = sum(1 for x in lengths if x > 35) / len(lengths)
        if long_share >= 0.4 or since >= 60:
            ov = ("met", f"{sum(1 for x in lengths if x > 35)} of your {len(lengths)} cycles were longer than 35 days (average {cs['mean']:.0f})")
        else:
            ov = ("not_met", f"Your cycles average {cs['mean']:.0f} days, mostly under 35")
    elif since >= 60:
        ov = ("met", f"It has been {since} days since your last period")
    else:
        ov = ("unknown", "Log at least 3 periods to judge this")
    hair, acne = effective_flag(profile, "excess_hair", logs, "hair_growth"), effective_flag(profile, "acne", logs, "acne")
    if hair == 1:
        hy = ("met", "You have extra hair growth, a common sign of high male hormones")
    elif acne == 1:
        hy = ("possible", "You have acne. That is a weaker sign on its own; a hormone blood test can clarify")
    elif hair == 0 and acne == 0:
        hy = ("not_met", "No extra hair growth or persistent acne")
    else:
        hy = ("unknown", "Tell us about acne and extra hair growth")
    tv = test_values(profile)
    fc, amh, scan, amhl = tv["follicle_count"], tv["AMH"], profile.get("scan"), profile.get("amh_level")
    if scan == "polycystic" or (scan is None and fc is not None and fc >= 20):
        mo = ("met", "Your ultrasound showed polycystic-looking ovaries (many small follicles)")
    elif scan == "normal" or (scan is None and fc is not None):
        mo = ("not_met", "Your ultrasound did not show polycystic-looking ovaries")
    elif amhl == "high" or (amh is not None and amh >= 5):
        mo = ("met", "Your AMH hormone blood test was high, which supports polycystic ovaries")
    elif amhl == "normal" or amh is not None:
        mo = ("not_met", "Your AMH hormone blood test was not high")
    else:
        mo = ("unknown", "Not checked yet. An ovary ultrasound (or an AMH blood test) would show this")
    crit = [{"key": "ovulatory", "name": "Periods far apart or missing", "status": ov[0], "detail": ov[1]},
            {"key": "androgen", "name": "Signs of high male hormones (extra hair, acne)", "status": hy[0], "detail": hy[1]},
            {"key": "ovaries", "name": "Ovary ultrasound or hormone blood test", "status": mo[0], "detail": mo[1]}]
    met = sum(c["status"] == "met" for c in crit)
    unknown = sum(c["status"] in ("unknown", "possible") for c in crit)
    if met >= 2:
        level, msg = "elevated", "Two of the three signs are present. A doctor should confirm this and rule out other causes."
    elif met + unknown < 2:
        level, msg = "low", "Fewer than two signs can be present, so PCOS looks unlikely."
    elif met == 1:
        level, msg = "watch", "One sign is present and others are still open. One more finding could settle it."
    else:
        level, msg = "insufficient", "We need a little more information to say."
    teen = profile.get("age") is not None and profile["age"] < 18
    if teen:
        level = "insufficient"
        msg = ("The standard PCOS criteria are not reliable in the first years after periods start, so we do not "
               "give a verdict under 18. Please see a doctor if cycles stay irregular or you have acne or extra hair.")
    return {"criteria": crit, "met": met, "unknown": unknown, "level": level, "summary": msg, "teen": teen}, hair, acne


def pcos_ml(profile, cs, hair, acne, ro, bundle, h_w_bmi):
    contra = bool(profile.get("hormonal_contraception"))
    inputs = {f: None for f in core.FEATURES}
    inputs["age"] = profile.get("age")
    inputs["BMI"] = h_w_bmi
    inputs["acne"], inputs["excess_hair"] = acne, hair
    inputs["weight_gain"] = profile.get("weight_gain")
    inputs.update(test_values(profile))
    if not contra and cs.get("n_cycles", 0) >= 3:
        inputs["cycle_irregular"] = 1.0 if (ro["criteria"][0]["status"] == "met" or cs["spread"] > 9) else 0.0
        inputs["cycle_length"] = float(min(max(cs["mean"], 20), 120))
    for f, (lo, hi, *_r) in core.SPEC.items():          # clamp to the model's trained ranges
        if inputs.get(f) is not None:
            inputs[f] = float(min(max(inputs[f], lo), hi))
    known = sum(v is not None for v in inputs.values())
    if known < 3 or ro.get("teen"):
        return None
    res = core.predict(inputs, bundle)
    nb = [n for n in core.next_best_input(inputs, bundle) if n["gain"] > 0.005][:3] if res["is_uncertain"] else []
    return {"result": res, "factors": core.explain(inputs, bundle), "next_best": nb, "inputs_used": inputs}


# ---------------------------------------------------------------- fingerprint
def fingerprint(logs, periods, maxday=40):
    """Average flow / pain / mood by cycle day (the 'cycle fingerprint')."""
    starts = [p["start"] for p in periods]
    acc = {i: {"pain": [], "mood": [], "flow": []} for i in range(1, maxday + 1)}
    for l in logs:
        day = d(l["date"])
        prev = [s for s in starts if s <= day]
        if not prev:
            continue
        cd = (day - prev[-1]).days + 1
        if cd > maxday:
            continue
        for k in ("pain", "mood", "flow"):
            if l.get(k) is not None:
                acc[cd][k].append(l[k])
    return [{"day": i, **{k: (round(mean(v), 2) if v else None) for k, v in acc[i].items()},
             "n": max(len(acc[i]["flow"]), len(acc[i]["pain"]), len(acc[i]["mood"]))} for i in acc]


# ---------------------------------------------------------------- main entry
def bmi_of(p):
    h, w = p.get("height_cm"), p.get("weight_kg")
    return round(w / ((h / 100) ** 2), 1) if h and w else None


def analyze(profile, logs, today, bundle):
    logs = sorted(logs, key=lambda l: l["date"])
    periods = find_periods(logs)
    cs = cycle_stats(periods, today)
    # An unlogged day is not a day without a period. If the person stopped logging, "days since last period"
    # (and every judgement built on it) would be an artefact of the gap, so we drop it and say so instead.
    stale_days = (today - d(logs[-1]["date"])).days if logs else 0
    if logs and stale_days > STALE_AFTER_DAYS:
        for k in ("cycle_day", "days_to_next", "predicted_next", "predicted_window_days"):
            cs.pop(k, None)
        cs["stale_days"] = stale_days
    recent_cover = sum(1 for l in logs if 0 <= (today - d(l["date"])).days < 30)
    bmi = bmi_of(profile)
    ro, hair, acne = rotterdam(profile, cs, logs, today)
    ml = pcos_ml(profile, cs, hair, acne, ro, bundle, bmi)

    pcos = {"id": "pcos", "name": "PCOS (a common hormone condition)", "level": ro["level"],
            "rotterdam": ro, "ml": ml, "teen": ro["teen"],
            "discuss": ["Ask for an ovary ultrasound and hormone blood tests (testosterone, AMH or LH/FSH, thyroid, prolactin) to confirm it and rule out look-alike conditions.",
                        "Ask about blood sugar and cholesterol checks, which matter for long-term health with PCOS."],
            "missing": [c["detail"] for c in ro["criteria"] if c["status"] in ("unknown", "possible")],
            "note": "PCOS is commonly missed: the WHO estimates up to 70% of affected women are undiagnosed."}
    conds = [pcos, endometriosis(logs, periods, profile), heavy_bleeding(logs, periods, profile),
             thyroid(logs, cs, profile), premenstrual(logs, periods)]
    conds += modules.extra_conditions(profile, modules.Sig(logs=logs), cs, conds[2]["score"])

    red = []
    recent = [l for l in logs if (today - d(l["date"])).days <= 7]
    red += modules.red_flags(profile, None, recent_logs=recent)
    chronic_pain = False
    for t in RED_TAGS:
        n = tag_days(recent, t)
        if not n:
            continue
        if t == "severe_pain" and n >= 4:          # a long-standing pattern, not a sudden event: keep the banner for real emergencies
            chronic_pain = True
            continue
        red.append(f"{TAGS[t]} logged in the last 7 days. Seek medical care promptly.")
    if cs.get("cycle_day", 0) >= 90 and recent_cover >= 8 and not profile.get("hormonal_contraception"):
        red.append(f"No period for {cs['cycle_day']} days. Take a pregnancy test and see a doctor if it is negative.")
    if tag_days(recent, "dizziness") and tag_days(recent, "flooding"):
        red.append("Dizziness with very heavy bleeding can mean significant blood loss. Get care today.")

    # next steps: the most useful single actions, ranked
    steps = []
    if "stale_days" in cs:
        steps.append({"title": "Log again to update your results",
                      "why": f"Your last entry was {cs['stale_days']} days ago, so cycle timing is not shown until you log again.", "kind": "log"})
    if chronic_pain:
        steps.append({"title": "See a doctor about ongoing severe pain",
                      "why": "You logged severe pain on 4 or more of the last 7 days. This pattern needs a proper check.", "kind": "test"})
    if ml and ml["next_best"]:
        n = ml["next_best"][0]
        steps.append({"title": f"Add your {n['label']}", "why": n["reason"], "kind": n["kind"]})
    for c in ro["criteria"]:
        if ro["level"] != "low" and c["status"] == "unknown" and c["key"] != "ovulatory":
            steps.append({"title": c["name"], "why": c["detail"], "kind": "test"})
    for c in conds[1:]:
        if c["level"] in ("watch", "elevated"):
            steps.append({"title": f"Discuss with a doctor: {c['name']}", "why": c["discuss"][0], "kind": "test"})
    if cs.get("n_cycles", 0) < 3:
        steps.append({"title": "Keep logging until you have 3 cycles", "why": "Cycle regularity cannot be judged reliably from fewer.", "kind": "log"})
    if len(logs) < 30:
        steps.append({"title": "Log for 30 days", "why": "Patterns in pain and mood need about a month to show.", "kind": "log"})

    return {
        "today": today.isoformat(),
        "profile_bmi": bmi,
        "evidence": {"logged_days": len(logs), "cycles": cs.get("n_cycles", 0),
                     "depth": min(1.0, round(0.5 * min(len(logs) / 90, 1) + 0.5 * min(cs.get("n_cycles", 0) / 3, 1), 2))},
        "cycle": {**cs, "labels": figo_labels(cs, profile.get("age")), "contraception": bool(profile.get("hormonal_contraception"))},
        "conditions": conds,
        "red_flags": red,
        "next_steps": steps[:4],
        "fingerprint": fingerprint(logs, periods),
        "symptom_counts": sorted(({"tag": t, "label": TAGS[t], "days": tag_days(logs, t)} for t in TAGS if tag_days(logs, t)),
                                 key=lambda r: -r["days"])[:8],
        "data_source": bundle["data_source"],
    }


# ---------------------------------------------------------------- quick check (questionnaire, no log needed)
BAND_LEN = {"short": 21, "normal": 29, "long": 40, "very_long": 55, "absent": 100}
BAND_TXT = {"short": "less than 24 days apart", "normal": "24 to 35 days apart", "long": "36 to 45 days apart",
            "very_long": "more than 45 days apart", "absent": "missing for 3 months or more"}
SPREAD = {"regular": 3, "varies": 10, "unpredictable": 20}


def _lvl(score, thr):
    return "elevated" if score >= thr[1] else "watch" if score >= thr[0] else "low"


def quick(a, bundle):
    """Score a 2-minute questionnaire with the same rules as the daily-log engine."""
    a = dict(a)
    fam = a.get("family_history") or []
    contra = bool(a.get("hormonal_contraception"))
    band, reg = a.get("cycle_band") or "unsure", a.get("regularity") or "regular"
    profile = {k: a.get(k) for k in ("age", "height_cm", "weight_kg", "acne", "excess_hair", "weight_gain",
                                     "scan", "amh_level", "lh_level", "life_stage", "hemoglobin", "diet")}
    profile.update(hormonal_contraception=contra, family_history=fam)
    # periods far apart / missing
    if contra:
        ov = ("unknown", "Hormonal contraception hides your natural cycle, so this cannot be judged")
    elif band in ("long", "very_long", "absent"):
        ov = ("met", f"You said your periods usually come {BAND_TXT[band]}")
    elif reg == "unpredictable" and band != "unsure":
        ov = ("possible", "You said your periods are unpredictable")
    elif band in ("short", "normal"):
        ov = ("not_met", f"You said your periods usually come {BAND_TXT[band]}")
    else:
        ov = ("unknown", "Tell us how far apart your periods usually are")
    ro, hair, acne = rotterdam(profile, {}, [], dt.date.today(), ov_override=ov)
    cs = {}
    if band in BAND_LEN and not contra:
        cs = {"n_cycles": 3, "mean": float(BAND_LEN[band]), "spread": SPREAD.get(reg, 3)}
    ml = pcos_ml(profile, cs, hair, acne, ro, bundle, bmi_of(profile))
    pcos = {"id": "pcos", "name": "PCOS (a common hormone condition)", "level": ro["level"], "rotterdam": ro, "ml": ml, "teen": ro["teen"],
            "discuss": [
                "Ask for an ovary ultrasound and hormone blood tests (testosterone, AMH or LH/FSH, thyroid, prolactin) to confirm it and rule out look-alike conditions.",
                "Ask about blood sugar and cholesterol checks, which matter for long-term health with PCOS."],
            "missing": [c["detail"] for c in ro["criteria"] if c["status"] in ("unknown", "possible")],
            "note": "PCOS is commonly missed: the WHO estimates up to 70% of affected women are undiagnosed."}

    def fill(base, ev, thr, maxs=9):
        sc = sum(e["points"] for e in ev)
        base.update(evidence=ev, score=sc, max_score=maxs, level=_lvl(sc, thr))
        return base

    pain = a.get("pain") or 0
    ev = []
    if pain >= 7: pts(ev, f"Severe period pain ({pain} out of 10)", 2)
    elif pain >= 5: pts(ev, f"Moderate to strong period pain ({pain} out of 10)", 1)
    if a.get("pain_other"): pts(ev, "Pelvic pain on days you are not bleeding", 2)
    if a.get("pain_sex"): pts(ev, "Pain during sex", 2)
    if a.get("bowel_urinary"): pts(ev, "Painful bowel movements or urination around your period", 2)
    if "endometriosis" in fam: pts(ev, "A close relative has endometriosis", 1)
    endo = fill(endometriosis([], [], {}), ev, (3, 5))

    ev = []
    if a.get("period_days") == "long": pts(ev, "Your periods last longer than 8 days", 2)
    if a.get("flow") == "very_heavy": pts(ev, "You soak through protection within an hour, or pass large clots", 3)
    elif a.get("flow") == "heavy": pts(ev, "Your flow is heavy", 2)
    if a.get("fatigue") and a.get("flow") in ("heavy", "very_heavy"): pts(ev, "Tiredness together with heavy bleeding can mean low iron", 1)
    if a.get("dizziness"): pts(ev, "You get dizzy or light-headed", 1)
    heavy = fill(heavy_bleeding([], [], {}), ev, (2, 4))

    ev = []
    for k, t in (("fatigue", "You feel tired much of the time"), ("hair_loss", "Your hair is thinning or falling out"),
                 ("cold", "You often feel unusually cold"), ("palpitations", "Your heart races at rest"),
                 ("low_mood", "Low mood most days"), ("weight_gain", "Weight gain you cannot explain")):
        if a.get(k) == 1 or a.get(k) is True: pts(ev, t, 1)
    if band in ("long", "very_long", "absent") or reg == "unpredictable": pts(ev, "Irregular periods (thyroid problems can cause this)", 1)
    if "thyroid" in fam: pts(ev, "A close relative has thyroid disease", 2)
    thy = fill(thyroid([], {}, {}), ev, (3, 5))

    ev = []
    if a.get("mood_before"): pts(ev, "Your mood drops in the week before most periods", 3)
    mood = fill(premenstrual([], []), ev, (1, 3), 4)
    if a.get("mood_before"): mood["note"] = "To confirm, doctors want daily mood ratings across 2 cycles. The Daily log tab records exactly that."

    conds = [pcos, endo, heavy, thy, mood]
    qc = (None, None, "Hormonal contraception hides your natural cycle, so cycle changes cannot be judged.") if contra else (
        reg in ("varies", "unpredictable"), band in ("very_long", "absent"), None)
    qsig = modules.Sig(quick=a)
    conds += modules.extra_conditions(profile, qsig, {}, heavy["score"], qc)
    red = modules.red_flags(profile, qsig)
    if a.get("fainting"): red.append("You have fainted recently. Please see a doctor promptly.")
    if a.get("severe_pain_now"): red.append("Sudden severe pain needs medical care today.")
    if a.get("soaking") and a.get("dizziness"): red.append("Very heavy bleeding with dizziness can mean significant blood loss. Get care today.")
    elif a.get("soaking"): red.append("Soaking through protection every hour needs medical attention soon.")
    steps = []
    if ml and ml["next_best"]:
        n = ml["next_best"][0]
        steps.append({"title": f"Get the {n['label']}", "why": n["reason"], "kind": n["kind"]})
    for c in ro["criteria"]:
        if ro["level"] in ("watch", "elevated") and c["status"] == "unknown" and c["key"] == "androgen":
            steps.append({"title": c["name"], "why": c["detail"], "kind": "question"})
    for c in conds[1:]:
        if c["level"] in ("watch", "elevated"):
            steps.append({"title": f"Discuss with a doctor: {c['name']}", "why": c["discuss"][0], "kind": "test"})
    steps.append({"title": "Track daily for a month", "why": "Dated logs turn 'my periods are bad' into proof a doctor can act on.", "kind": "log"})
    labels = [f"You said your periods usually come {BAND_TXT[band]}"] if band in BAND_TXT else []
    return {
        "mode": "quick", "today": dt.date.today().isoformat(), "profile_bmi": bmi_of(profile),
        "evidence": {"logged_days": 0, "cycles": 0, "depth": 0.0},
        "cycle": {"n_cycles": 0, "lengths": [], "durations": [], "labels": labels, "contraception": contra},
        "conditions": conds, "red_flags": red, "next_steps": steps[:4], "fingerprint": [], "symptom_counts": [],
        "data_source": bundle["data_source"],
    }
