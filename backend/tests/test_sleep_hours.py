from datetime import date
import pytest
from pydantic import ValidationError
from app.schemas import SymptomIn


def test_symptom_accepts_sleep_hours():
    data = SymptomIn(symptom="Fatigue", recorded_on=date(2026, 10, 24), severity=4, sleep_hours=7.5)
    assert data.sleep_hours == 7.5


def test_sleep_hours_must_be_within_day():
    with pytest.raises(ValidationError):
        SymptomIn(symptom="Fatigue", recorded_on=date(2026, 10, 24), severity=4, sleep_hours=25)
