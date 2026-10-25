from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    AssistantQuestion, QuickCycleIn, analyze_cycle, create_report,
    create_symptom, current_user, delete_account, delete_all_health_data,
    delete_cycle_day, delete_symptom, export_data, get_cycle_profile,
    health, health_assistant, list_cycle_days, list_symptoms, login,
    quick_cycle_screen, register, save_cycle_day, save_cycle_profile, update_symptom,
)
from app.schemas import LoginIn, RegisterIn, SymptomIn


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'integration.sqlite3'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autoflush=False, autocommit=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_user(db, email):
    response = register(RegisterIn(name="Synthetic Tester", email=email, password="test-only-passphrase"), db)
    return response["user"], response["access_token"]


def authenticated_user(db, token):
    return current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)


def test_registration_login_and_authentication(db):
    assert health()["status"] == "ok"
    user, token = create_user(db, "synthetic-a@example.com")
    assert user.email == "synthetic-a@example.com"
    assert login(LoginIn(email=user.email, password="test-only-passphrase"), db)["user"].id == user.id
    assert authenticated_user(db, token).id == user.id
    with pytest.raises(HTTPException) as unauthenticated:
        current_user(None, db)
    assert unauthenticated.value.status_code == 401
    with pytest.raises(HTTPException) as duplicate:
        register(RegisterIn(name="Synthetic Tester", email=user.email, password="test-only-passphrase"), db)
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as bad_password:
        login(LoginIn(email=user.email, password="wrong-password"), db)
    assert bad_password.value.status_code == 401


def test_user_scoped_symptom_crud_and_insights(db):
    owner, _ = create_user(db, "owner@example.com")
    other, _ = create_user(db, "other@example.com")
    payload = SymptomIn(symptom="Headache", recorded_on=date.today(), severity=6, description="synthetic record")
    entry = create_symptom(payload, db, owner)
    assert len(list_symptoms(None, None, db, owner)) == 1
    assert list_symptoms(None, None, db, other) == []
    with pytest.raises(HTTPException) as denied_update:
        update_symptom(entry.id, payload, db, other)
    assert denied_update.value.status_code == 404
    updated = update_symptom(entry.id, payload.model_copy(update={"severity":8}), db, owner)
    assert updated.severity == 8
    with pytest.raises(HTTPException) as denied_delete:
        delete_symptom(entry.id, db, other)
    assert denied_delete.value.status_code == 404
    assert delete_symptom(entry.id, db, owner).status_code == 204


def test_cycle_records_screening_pdf_export_and_deletion(db):
    user, _ = create_user(db, "cycle@example.com")
    profile = save_cycle_profile({"age":29,"life_stage":"postpartum","acne":0}, db, user)
    assert profile["age"] == 29
    first = save_cycle_day({"recorded_on":date.today().isoformat(),"flow":3,"pain":2,"tags":["cramps"]}, db, user)
    second = save_cycle_day({"recorded_on":(date.today() - timedelta(days=1)).isoformat(),"flow":0,"tags":[]}, db, user)
    assert len(list_cycle_days(db, user)) == 2
    full = analyze_cycle(db, user)
    assert full["evidence"]["logged_days"] == 2
    quick = quick_cycle_screen(QuickCycleIn(age=29, life_stage="postpartum", phq_interest=2, phq_down=2), user)
    assert any("PHQ-2" in item["text"] for condition in quick["conditions"] for item in condition.get("evidence", []))
    report = create_report({"sections":["entries","cycles","observations","questions"]}, db, user)
    assert report.media_type == "application/pdf" and report.body.startswith(b"%PDF")
    export = export_data(db, user)
    assert b'"cycle_days"' in export.body and b'"cycle_profile"' in export.body
    assert get_cycle_profile(db, user)["life_stage"] == "postpartum"
    assert delete_cycle_day(first["id"], db, user).status_code == 204
    delete_all_health_data(db, user)
    assert list_cycle_days(db, user) == []
    assert get_cycle_profile(db, user) == {}
    delete_account(db, user)
    with pytest.raises(HTTPException) as deleted_account:
        authenticated_user(db, _)
    assert deleted_account.value.status_code == 401


def test_assistant_fallback_is_explicit(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    answer = health_assistant(AssistantQuestion(question="How can I track my period?"))
    assert answer["mode"] == "demo"
    assert "Periods and cycle patterns vary" in answer["answer"]
