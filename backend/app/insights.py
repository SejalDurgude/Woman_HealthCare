from collections import Counter, defaultdict
from datetime import date, timedelta

def build_insights(entries, today=None):
    """Deterministic descriptive analytics; never a diagnosis."""
    today = today or date.today()
    start = today - timedelta(days=29)
    recent = [e for e in entries if start <= e.recorded_on <= today]
    days_logged = len({e.recorded_on for e in recent})
    symptom_days = defaultdict(set)
    severities = defaultdict(list)
    for e in recent:
        key = e.symptom.strip().lower()
        symptom_days[key].add(e.recorded_on)
        severities[key].append(e.severity)
    frequency = []
    for key, days in symptom_days.items():
        frequency.append({
            "symptom": key.title(),
            "distinct_days": len(days),
            "entries": sum(1 for e in recent if e.symptom.strip().lower() == key),
            "average_severity": round(sum(severities[key]) / len(severities[key]), 1),
            "dates": sorted(d.isoformat() for d in days),
            "period_start": start.isoformat(),
            "period_end": today.isoformat(),
        })
    frequency.sort(key=lambda x: (-x["distinct_days"], x["symptom"]))
    severity_by_day = defaultdict(list)
    for e in recent:
        severity_by_day[e.recorded_on.isoformat()].append(e.severity)
    trend = [{"date": d, "average_severity": round(sum(v)/len(v), 1), "entries": len(v)} for d, v in sorted(severity_by_day.items())]
    observations = []
    if days_logged < 4:
        observations.append({"title": "Keep building your timeline", "text": f"You have records on {days_logged} distinct day(s) in the last 30 days. Add entries over time to make personal trends easier to review.", "basis": f"{days_logged} distinct logged days between {start.isoformat()} and {today.isoformat()}.", "level": "limited-data"})
    else:
        observations.append({"title": "Your timeline is taking shape", "text": f"You logged symptoms on {days_logged} distinct days in the last 30 days. This is a record of entries, not a measure of how many days you were unwell.", "basis": f"Counted distinct dates with at least one entry from {start.isoformat()} to {today.isoformat()}.", "level": "info"})
    for item in frequency[:3]:
        observations.append({"title": f"{item['symptom']} appears in your records", "text": f"{item['symptom']} was recorded on {item['distinct_days']} distinct day(s), across {item['entries']} entr(y/ies), in the last 30 days. Average recorded severity: {item['average_severity']}/10.", "basis": f"Dates: {', '.join(item['dates'])}. Window: {item['period_start']} to {item['period_end']}.", "level": "pattern"})
    cooccur = []
    symptom_names = sorted(symptom_days.keys())
    for i, a in enumerate(symptom_names):
        for b in symptom_names[i+1:]:
            shared = sorted(symptom_days[a] & symptom_days[b])
            if len(shared) >= 2:
                cooccur.append({"symptom_a": a.title(), "symptom_b": b.title(), "shared_days": len(shared), "dates": [d.isoformat() for d in shared]})
    return {"window_days": 30, "period_start": start.isoformat(), "period_end": today.isoformat(), "distinct_logged_days": days_logged, "total_entries": len(recent), "frequency": frequency, "severity_trend": trend, "observations": observations, "cooccurrence": cooccur, "disclaimer": "These are descriptions of your saved records, not diagnoses. Missing entries do not mean symptoms were absent. Co-occurrence does not establish cause."}
