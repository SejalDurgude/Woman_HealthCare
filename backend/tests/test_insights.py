from datetime import date
from types import SimpleNamespace
from app.insights import build_insights

def test_frequency_counts_distinct_days_not_only_entries():
    entries = [
        SimpleNamespace(symptom="Headache", recorded_on=date(2026, 10, 20), severity=4),
        SimpleNamespace(symptom="Headache", recorded_on=date(2026, 10, 20), severity=6),
        SimpleNamespace(symptom="Fatigue", recorded_on=date(2026, 10, 21), severity=3),
    ]
    result = build_insights(entries, today=date(2026, 10, 24))
    headache = next(x for x in result["frequency"] if x["symptom"] == "Headache")
    assert headache["entries"] == 2
    assert headache["distinct_days"] == 1
    assert headache["average_severity"] == 5.0

def test_insufficient_data_is_explicit():
    result = build_insights([], today=date(2026, 10, 24))
    assert result["distinct_logged_days"] == 0
    assert result["observations"][0]["level"] == "limited-data"
