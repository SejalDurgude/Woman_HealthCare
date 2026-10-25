"""Life-stage modules: midlife (perimenopause), anaemia, and pregnancy / postpartum wellbeing.

Same design rules as insights.py: every point is shown with its evidence, thresholds come from
published guidance, and nothing here diagnoses. The same engines score both the daily log and the
2-minute questionnaire through the small `Sig` adapter, so the two modes can never drift apart.

Sources the thresholds follow (verify before clinical use):
- Perimenopause staging: STRAW+10 (persistent 7+ day change in cycle length = early transition,
  60+ days without a period = late transition, 12 months without = menopause).
- Anaemia cut-offs: WHO haemoglobin thresholds (non-pregnant women < 12.0 g/dL, pregnant < 11.0 g/dL;
  severity bands mild / moderate / severe).
- Pregnancy danger signs and perinatal mood: WHO / national maternal-health guidance. Triage only.
"""
from statistics import mean

# tags added by these modules (merged into insights.TAGS)
NEW_TAGS = {
    "hot_flash": "Hot flushes", "night_sweats": "Night sweats", "poor_sleep": "Poor sleep",
    "brain_fog": "Brain fog or poor memory", "vaginal_dryness": "Vaginal dryness", "joint_pain": "Aching joints",
    "breathless": "Breathless on light effort", "pica": "Craving ice, clay or other non-food items",
    "brittle_nails": "Brittle or spoon-shaped nails", "pale": "Looking paler than usual",
    "anhedonia": "Little interest or joy in things", "self_harm_thoughts": "Thoughts of harming myself",
    "severe_headache": "Severe headache that will not go", "vision_changes": "Blurred vision or flashing lights",
    "reduced_movement": "Baby moving much less than usual", "sudden_swelling": "Sudden swelling of face or hands",
    "fever": "Fever or chills", "heavy_pp_bleed": "Heavy bleeding in pregnancy or after birth",
}
MATERNAL_RED = {"severe_headache", "vision_changes", "reduced_movement", "sudden_swelling", "fever", "heavy_pp_bleed"}
RED_TAGS_NEW = MATERNAL_RED | {"self_harm_thoughts"}

CRISIS_TEXT = ("You told us you have had thoughts of harming yourself. You deserve support right now. "
               "Please talk to someone you trust, call your local emergency number (112 in India), or a crisis line "
               "(in India, Tele-MANAS: 14416). If you are in another country, search for your national crisis line.")

STAGES = ("reproductive", "pregnant", "postpartum", "midlife")
STAGE_TXT = {"reproductive": "Periods and cycles", "pregnant": "Pregnant", "postpartum": "Had a baby in the last year",
             "midlife": "Changes around midlife"}

# WHO haemoglobin (g/dL): (anaemia below, moderate below, severe below)
HB_CUT = {"nonpregnant": (12.0, 11.0, 8.0), "pregnant": (11.0, 10.0, 7.0)}


class Sig:
    """Adapter: asks 'does this symptom show up enough to count?' for logs or for questionnaire answers."""

    def __init__(self, logs=None, quick=None):
        self.logs, self.q = logs, quick
        self.n = len(logs) if logs is not None else 1

    @property
    def is_quick(self):
        return self.q is not None

    def days(self, tag):
        if self.is_quick:
            return 1 if self.q.get(tag) else 0
        return sum(1 for l in self.logs if tag in (l.get("tags") or []))

    def hit(self, tag, min_days=3, share=0.0):
        if self.is_quick:
            return bool(self.q.get(tag))
        d = self.days(tag)
        return d >= min_days and d / max(self.n, 1) >= share

    def hit_any(self, tags, min_days=3):
        if self.is_quick:
            return any(self.q.get(t) for t in tags)
        return sum(self.days(t) for t in tags) >= min_days


def _pts(ev, text, p):
    ev.append({"text": text, "points": p})
    return p


def _finish(id_, name, score, maxs, ev, thr, n_logs, min_logs, **extra):
    if n_logs < min_logs:
        level = "insufficient"
    elif score >= thr[1]:
        level = "elevated"
    elif score >= thr[0]:
        level = "watch"
    else:
        level = "low"
    return {"id": id_, "name": name, "level": level, "score": score, "max_score": maxs, "evidence": ev, **extra}


# ---------------------------------------------------------------- perimenopause
def cycle_signals(cs, profile):
    """(variable, long_gap, note) from log-derived cycle stats."""
    if profile.get("hormonal_contraception"):
        return None, None, "Hormonal contraception hides your natural cycle, so cycle changes cannot be judged."
    lengths = cs.get("lengths", [])
    variable = None
    if len(lengths) >= 3:
        jumps = sum(1 for a, b in zip(lengths, lengths[1:]) if abs(b - a) >= 7)
        variable = jumps >= 2
    long_gap = bool(lengths and max(lengths) >= 60) or cs.get("cycle_day", 0) >= 60
    return variable, long_gap, None


def wants_perimenopause(profile, sig):
    age = profile.get("age")
    return (age is not None and age >= 38) or profile.get("life_stage") == "midlife" \
        or sig.hit_any(["hot_flash", "night_sweats"], 3 if not sig.is_quick else 1)


def perimenopause(profile, sig, variable, long_gap, note=None):
    ev, s = [], 0
    age = profile.get("age")
    if age is not None and age >= 45:
        s += _pts(ev, f"Age {age:g}: perimenopause most often begins in the mid-40s", 2)
    elif age is not None and age >= 40:
        s += _pts(ev, f"Age {age:g}: perimenopause can begin from the early 40s", 1)
    if variable:
        s += _pts(ev, "Cycle length keeps jumping by a week or more from one cycle to the next", 2)
    if long_gap:
        s += _pts(ev, "A gap of about 60 days or more between periods (a marker of late transition)", 2)
    if sig.hit_any(["hot_flash", "night_sweats"], 3 if not sig.is_quick else 1):
        s += _pts(ev, "Hot flushes or night sweats", 2)
    if sig.hit("poor_sleep", 5, 0.2):
        s += _pts(ev, "Poor sleep on many days", 1)
    if sig.hit("brain_fog", 3):
        s += _pts(ev, "Brain fog or poor memory", 1)
    if sig.hit("joint_pain", 3):
        s += _pts(ev, "Aching joints", 1)
    if sig.hit("vaginal_dryness", 3):
        s += _pts(ev, "Vaginal dryness", 1)
    discuss = ["Ask whether your symptoms fit perimenopause. It is usually a clinical call from age, symptoms and cycle pattern, "
               "and a hormone test is often not needed over 45.",
               "Ask for a TSH test and a blood count, because thyroid problems and low iron look similar to perimenopause.",
               "Ask about managing hot flushes and sleep, and about bone, heart and blood pressure checks at this stage."]
    if age is not None and age < 40 and s >= 3:
        discuss.insert(0, "Cycle and menopause-type symptoms before 40 deserve prompt review (early ovarian insufficiency is treatable and matters for bone and heart health).")
    r = _finish("perimenopause", "Perimenopause (the change before menopause)", s, 11, ev, (3, 5), sig.n, 14 if not sig.is_quick else 0,
                discuss=discuss,
                missing=["Log flow every bleeding day and tag hot flushes, night sweats and sleep"],
                note=note or "Perimenopause is easy to miss because it can start years before periods stop. Hormone levels swing day to day, so one blood test is rarely decisive.")
    return r


# ---------------------------------------------------------------- anaemia
def hb_status(profile):
    """(level, text) from a user-entered haemoglobin, or None."""
    hb = profile.get("hemoglobin")
    if hb is None:
        return None
    preg = profile.get("life_stage") == "pregnant"
    low, mod, sev = HB_CUT["pregnant" if preg else "nonpregnant"]
    if hb < sev:
        return "severe", f"Haemoglobin {hb:g} g/dL is severely low"
    if hb < mod:
        return "moderate", f"Haemoglobin {hb:g} g/dL is moderately low"
    if hb < low:
        return "mild", f"Haemoglobin {hb:g} g/dL is mildly low"
    return "normal", f"Haemoglobin {hb:g} g/dL is in the normal range"


def anaemia(profile, sig, heavy_score, n_logs):
    ev, s = [], 0
    hb = hb_status(profile)
    if hb and hb[0] != "normal":
        s += _pts(ev, hb[1] + " (WHO cut-off " + ("11" if profile.get("life_stage") == "pregnant" else "12") + " g/dL)", 5)
    if heavy_score >= 2:
        s += _pts(ev, "Heavy or long periods are the most common cause of iron loss", 2)
    if sig.hit("fatigue", 5, 0.25):
        s += _pts(ev, "Tiredness on many days", 1)
    if sig.hit("dizziness", 2):
        s += _pts(ev, "Dizziness or light-headedness", 1)
    if sig.hit("breathless", 2):
        s += _pts(ev, "Breathless on light effort", 1)
    if sig.hit("pica", 1):
        s += _pts(ev, "Cravings for ice, clay or other non-food items, a classic iron-deficiency sign", 2)
    if sig.hit_any(["brittle_nails", "pale", "hair_loss"], 3 if not sig.is_quick else 1):
        s += _pts(ev, "Pale skin, brittle nails or hair loss", 1)
    diet = profile.get("diet")
    if diet in ("veg", "vegan"):
        s += _pts(ev, "A vegetarian or vegan diet makes iron and B12 shortfalls more likely", 1)
    if profile.get("life_stage") in ("pregnant", "postpartum"):
        s += _pts(ev, "Pregnancy and the months after birth raise iron needs sharply", 1)
    if hb and hb[0] == "normal":
        s += _pts(ev, hb[1] + ", so anaemia is unlikely (iron stores can still be low, a ferritin test checks that)", -3)
    s = max(s, 0)
    discuss = ["Ask for a complete blood count (haemoglobin) and a ferritin test. Ferritin shows low iron before anaemia appears.",
               "If iron is low, ask which supplement and dose suit you, and for how long. Do not start high doses without a test.",
               "If periods are heavy, ask what is causing it. Treating the iron without treating the bleeding does not last."]
    missing = ["Add your latest haemoglobin value (from any blood count) in About me"]
    r = _finish("anaemia", "Anaemia (low haemoglobin)", s, 14, ev, (3, 5), sig.n, 14 if not sig.is_quick else 0,
                discuss=discuss, missing=missing,
                note="More than half of women aged 15 to 49 in India are anaemic (NFHS-5). It is common, cheap to test and treatable, but it is often missed.")
    if hb and hb[0] != "normal":
        r["level"] = "elevated" if hb[0] in ("moderate", "severe") or s >= 7 else "watch"
    return r


def anaemia_red_flag(profile):
    hb = hb_status(profile)
    if hb and hb[0] == "severe":
        return f"{hb[1]}. Please see a doctor promptly, severe anaemia needs treatment."
    return None


# ---------------------------------------------------------------- pregnancy and postpartum
def maternal(profile, sig):
    """Danger-sign triage plus perinatal mood. Awareness and triage only."""
    stage = profile.get("life_stage")
    ev, s = [], 0
    danger = [t for t in sorted(MATERNAL_RED) if sig.hit(t, 1)]
    if danger:
        s += _pts(ev, "Warning signs reported: " + ", ".join(NEW_TAGS[t].lower() for t in danger), 4)
    # PHQ-2 (public domain): two questions, each 0-3 for the last two weeks; a total of 3 or more is a positive screen.
    if sig.is_quick and (sig.q.get("phq_interest") is not None or sig.q.get("phq_down") is not None):
        phq = int(sig.q.get("phq_interest") or 0) + int(sig.q.get("phq_down") or 0)
        if phq >= 3:
            s += _pts(ev, f"Mood questions (PHQ-2) scored {phq} out of 6. A score of 3 or more is a positive screen", 3)
    if sig.hit("low_mood", 5, 0.3):
        s += _pts(ev, "Low mood on many days", 2)
    if sig.hit("anhedonia", 3):
        s += _pts(ev, "Little interest or joy in things", 2)
    if sig.hit("anxiety", 5, 0.3):
        s += _pts(ev, "Anxiety on many days", 1)
    if sig.hit("poor_sleep", 5, 0.4):
        s += _pts(ev, "Poor sleep beyond what the baby explains", 1)
    if sig.hit("self_harm_thoughts", 1):
        s += _pts(ev, "Thoughts of self-harm", 4)
    who = "pregnancy" if stage == "pregnant" else "the months after birth"
    return _finish("maternal", "Pregnancy and postpartum wellbeing", s, 14, ev, (2, 4), sig.n, 7 if not sig.is_quick else 0,
                   discuss=["Tell your antenatal or postnatal provider about these symptoms. Mood screening is a routine part of care in " + who + " and it is very treatable.",
                            "Ask which warning signs mean you should go to hospital without waiting for the next visit.",
                            "Ask for a haemoglobin and blood pressure check if you have not had one recently."],
                   missing=["Log mood, sleep and any warning signs each day"],
                   note="Low mood and anxiety affect many women in pregnancy and after birth. It is common, not a failing, and help works.")


def extra_conditions(profile, sig, cs, heavy_score, quick_cycle=None):
    """Perimenopause (when relevant), anaemia, and maternal wellbeing (when pregnant or postpartum).

    quick_cycle = (variable, long_gap, note) derived from questionnaire answers; logs derive it from cs.
    """
    out = []
    variable, long_gap, note = quick_cycle if sig.is_quick else cycle_signals(cs, profile)
    if wants_perimenopause(profile, sig):
        out.append(perimenopause(profile, sig, variable, long_gap, note))
    out.append(anaemia(profile, sig, heavy_score, sig.n))
    if profile.get("life_stage") in ("pregnant", "postpartum"):
        out.append(maternal(profile, sig))
    return out


def red_flags(profile, sig, recent_logs=None):
    """Extra urgent messages. For logs, only the last 7 days count (recent_logs)."""
    out = []
    src = Sig(logs=recent_logs) if recent_logs is not None else sig
    for t in sorted(MATERNAL_RED):
        if src.hit(t, 1):
            out.append(f"{NEW_TAGS[t]}. In pregnancy or after birth this needs medical care today.")
    if src.hit("self_harm_thoughts", 1):
        out.insert(0, CRISIS_TEXT)
    a = anaemia_red_flag(profile)
    if a:
        out.append(a)
    return out
