import io, json, os
import sys
from pathlib import Path
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, inspect, text
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from .database import Base, engine, get_db
from .models import User, SymptomEntry, CycleDay, CycleProfile
from .schemas import RegisterIn, LoginIn, TokenOut, UserOut, SymptomIn, SymptomOut
from .security import hash_password, verify_password, create_access_token, decode_access_token
from .insights import build_insights
from .resources import RESOURCES
from pydantic import BaseModel, Field
from typing import Literal
from .ml_patterns import analyze_patterns

Base.metadata.create_all(bind=engine)
# CycleLens screening engines are bundled here as a single integrated feature.
sys.path.insert(0, str(Path(__file__).with_name("cycle_engine")))
import insights as cycle_insights
import core as cycle_core
import modules as cycle_modules
_cycle_bundle = None

def get_cycle_bundle():
    global _cycle_bundle
    if _cycle_bundle is None:
        if not os.path.exists(cycle_core.MODEL_PATH):
            import train as cycle_train
            cycle_train.main(quiet=True)
        _cycle_bundle = cycle_core.load_bundle()
    return _cycle_bundle
# Lightweight additive migration for existing SQLite installations.
try:
    if engine.dialect.name == "sqlite":
        columns = {c["name"] for c in inspect(engine).get_columns("symptom_entries")}
        if "sleep_hours" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE symptom_entries ADD COLUMN sleep_hours FLOAT"))
except Exception:
    pass
app = FastAPI(title="HerHealth Lens API", version="1.0.0", description="Private symptom tracking and explainable descriptive insights. Not a diagnostic service.")
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5174")
app.add_middleware(CORSMiddleware, allow_origins=list({origin, "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"}), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)

@app.get("/api/health")
def health():
    return {"status":"ok", "app":"HerHealth Lens", "medical_notice":"For tracking and education only; not a diagnosis."}

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired. Please log in again.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found. Please log in again.")
    return user

@app.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token":create_access_token(user.id), "user":user}

@app.post("/api/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"access_token":create_access_token(user.id), "user":user}

@app.get("/api/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user

@app.get("/api/symptoms", response_model=list[SymptomOut])
def list_symptoms(start: date | None = None, end: date | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(SymptomEntry).where(SymptomEntry.owner_id == user.id)
    if start: query = query.where(SymptomEntry.recorded_on >= start)
    if end: query = query.where(SymptomEntry.recorded_on <= end)
    return list(db.scalars(query.order_by(SymptomEntry.recorded_on.desc(), SymptomEntry.id.desc())).all())

@app.post("/api/symptoms", response_model=SymptomOut, status_code=201)
def create_symptom(data: SymptomIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = SymptomEntry(**data.model_dump(), owner_id=user.id)
    db.add(entry); db.commit(); db.refresh(entry)
    return entry

@app.put("/api/symptoms/{entry_id}", response_model=SymptomOut)
def update_symptom(entry_id: int, data: SymptomIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = db.scalar(select(SymptomEntry).where(SymptomEntry.id == entry_id, SymptomEntry.owner_id == user.id))
    if not entry: raise HTTPException(status_code=404, detail="Symptom entry not found.")
    for key, value in data.model_dump().items(): setattr(entry, key, value)
    db.commit(); db.refresh(entry); return entry

@app.delete("/api/symptoms/{entry_id}", status_code=204)
def delete_symptom(entry_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = db.scalar(select(SymptomEntry).where(SymptomEntry.id == entry_id, SymptomEntry.owner_id == user.id))
    if not entry: raise HTTPException(status_code=404, detail="Symptom entry not found.")
    db.delete(entry); db.commit(); return Response(status_code=204)

@app.get("/api/insights")
def insights(db: Session = Depends(get_db), user: User = Depends(current_user)):
    entries = list(db.scalars(select(SymptomEntry).where(SymptomEntry.owner_id == user.id).order_by(SymptomEntry.recorded_on)).all())
    return build_insights(entries)


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)

class CycleProfileIn(BaseModel):
    age: float | None = Field(None, ge=10, le=65)
    height_cm: float | None = Field(None, ge=120, le=220)
    weight_kg: float | None = Field(None, ge=30, le=250)
    acne: int | None = Field(None, ge=0, le=1)
    excess_hair: int | None = Field(None, ge=0, le=1)
    weight_gain: int | None = Field(None, ge=0, le=1)
    hormonal_contraception: bool = False
    family_history: list[str] = []
    LH_FSH_ratio: float | None = Field(None, ge=.1, le=6)
    AMH: float | None = Field(None, ge=.1, le=20)
    follicle_count: float | None = Field(None, ge=0, le=40)
    scan: Literal["polycystic","normal"] | None = None
    amh_level: Literal["high","normal"] | None = None
    lh_level: Literal["high","normal"] | None = None
    life_stage: Literal["reproductive","pregnant","postpartum","midlife"] | None = None
    hemoglobin: float | None = Field(None, ge=3, le=20)
    diet: Literal["nonveg","veg","vegan"] | None = None

class QuickCycleIn(CycleProfileIn):
    cycle_band: Literal["short","normal","long","very_long","absent","unsure"] | None = None
    regularity: Literal["regular","varies","unpredictable"] | None = None
    flow: Literal["light","heavy","very_heavy"] | None = None
    period_days: Literal["normal","long"] | None = None
    pain: int | None = Field(None, ge=0, le=10)
    pain_other: bool = False
    pain_sex: bool = False
    bowel_urinary: bool = False
    fatigue: bool = False
    dizziness: bool = False
    fainting: bool = False
    soaking: bool = False
    severe_pain_now: bool = False
    mood_before: bool = False
    hot_flash: bool = False
    night_sweats: bool = False
    poor_sleep: bool = False
    brain_fog: bool = False
    joint_pain: bool = False
    vaginal_dryness: bool = False
    breathless: bool = False
    pica: bool = False
    brittle_nails: bool = False
    pale: bool = False
    anhedonia: bool = False
    low_mood: bool = False
    anxiety: bool = False
    self_harm_thoughts: bool = False
    severe_headache: bool = False
    vision_changes: bool = False
    reduced_movement: bool = False
    sudden_swelling: bool = False
    fever: bool = False
    heavy_pp_bleed: bool = False
    phq_interest: int | None = Field(None, ge=0, le=3)
    phq_down: int | None = Field(None, ge=0, le=3)

@app.post("/api/assistant/chat")
def health_assistant(data: AssistantQuestion):
    """General health education assistant; not a diagnostic or triage service."""
    question = data.question.strip()
    api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=os.getenv("AI_MODEL", "gpt-4o-mini"),
                temperature=0.3,
                max_tokens=500,
                messages=[
                    {"role":"system","content":(
                        "You are HerHealth Lens, a supportive women's-health education assistant. "
                        "Provide general, evidence-informed education and practical questions to ask a clinician. "
                        "Never diagnose, prescribe, claim certainty, or suggest stopping medication. "
                        "For severe, sudden, or rapidly worsening symptoms, advise urgent local medical care. "
                        "For possible pregnancy complications, heavy bleeding with faintness, chest pain, or trouble breathing, "
                        "recommend emergency care. Be nonjudgmental and concise. State that information is educational, "
                        "not a substitute for a qualified clinician. Do not ask for identifying details."
                    )},
                    {"role":"user","content":question}
                ]
            )
            answer = response.choices[0].message.content or "I couldn't form a response. Please try again."
            return {"answer":answer, "mode":"ai"}
        except Exception:
            # Do not expose provider errors or credentials.
            pass
    q = question.lower()
    if any(w in q for w in ["period", "menstrual", "cycle", "cramp"]):
        answer = "Periods and cycle patterns vary. It can help to record start dates, bleeding changes, pain intensity, duration, medicines taken, and how symptoms affect daily activities. Consider discussing new, persistent, severe, or disruptive symptoms with a healthcare professional. This is general education, not a diagnosis."
    elif any(w in q for w in ["stress", "anxious", "anxiety", "relax", "sleep", "mood"]):
        answer = "A gentle starting point may be a slow comfortable breathing exercise, a short walk, a regular sleep routine, or talking with someone you trust. Choose what feels safe and manageable for you. If distress persists, affects daily life, or you feel unsafe, consider professional support."
    elif any(w in q for w in ["doctor", "appointment", "clinic", "prepare", "track"]):
        answer = "Before an appointment, consider noting when symptoms began, how often they happen, severity (0–10), duration, your cycle context if relevant, medicines or supplements, and questions you want answered. Bring only information you feel comfortable sharing. A clinician can help interpret the pattern in context."
    elif any(w in q for w in ["screen", "checkup", "prevent", "vaccine", "health check"]):
        answer = "Preventive care depends on your age, history, symptoms, and local guidance. A primary-care clinician can help you understand which screenings, vaccinations, and checks are appropriate for you. The Health Library links to public health information for further reading."
    else:
        answer = "I can help with general women's-health education, symptom tracking, cycle basics, preventive-care questions, stress-management ideas, and preparing for appointments. Could you share a little more about the general topic (without personal identifying details)? I can’t diagnose or tell you whether a symptom is safe to ignore. For severe, sudden, or rapidly worsening symptoms, seek urgent medical care."
    return {"answer":answer, "mode":"demo"}

@app.get("/api/insights/ml")
def ml_insights(db: Session = Depends(get_db), user: User = Depends(current_user)):
    entries = list(db.scalars(select(SymptomEntry).where(SymptomEntry.owner_id == user.id).order_by(SymptomEntry.recorded_on)).all())
    return analyze_patterns(entries)

@app.get("/api/cycle/days")
def list_cycle_days(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(CycleDay).where(CycleDay.owner_id == user.id).order_by(CycleDay.recorded_on)).all()
    return [{"id":r.id,"recorded_on":r.recorded_on.isoformat(),"flow":r.flow,"pain":r.pain,"mood":r.mood,"energy":r.energy,"tags":r.tags or [],"notes":r.notes} for r in rows]

@app.put("/api/cycle/days")
def save_cycle_day(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try: day = date.fromisoformat(body["recorded_on"])
    except Exception: raise HTTPException(status_code=422, detail="A valid recorded_on date is required.")
    if day > date.today(): raise HTTPException(status_code=422, detail="Future dates cannot be logged.")
    flow = body.get("flow", 0); pain = body.get("pain"); mood = body.get("mood"); energy = body.get("energy")
    if not isinstance(flow, int) or not 0 <= flow <= 4: raise HTTPException(status_code=422, detail="Flow must be between 0 and 4.")
    if pain is not None and (not isinstance(pain,int) or not 0 <= pain <= 10): raise HTTPException(status_code=422, detail="Pain must be between 0 and 10.")
    tags = body.get("tags") or []
    if not isinstance(tags,list) or any(t not in cycle_insights.TAGS for t in tags): raise HTTPException(status_code=422, detail="One or more symptom tags are not supported.")
    row = db.scalar(select(CycleDay).where(CycleDay.owner_id == user.id, CycleDay.recorded_on == day))
    if row is None: row = CycleDay(owner_id=user.id, recorded_on=day); db.add(row)
    row.flow=flow; row.pain=pain; row.mood=mood; row.energy=energy; row.tags=tags; row.notes=str(body.get("notes") or "")[:1000]
    db.commit(); db.refresh(row)
    return {"id":row.id,"recorded_on":row.recorded_on.isoformat(),"flow":row.flow,"pain":row.pain,"mood":row.mood,"energy":row.energy,"tags":row.tags or [],"notes":row.notes}

@app.delete("/api/cycle/days/{day_id}", status_code=204)
def delete_cycle_day(day_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row=db.scalar(select(CycleDay).where(CycleDay.id==day_id,CycleDay.owner_id==user.id))
    if not row: raise HTTPException(status_code=404, detail="Cycle log not found.")
    db.delete(row); db.commit(); return Response(status_code=204)

@app.get("/api/cycle/profile")
def get_cycle_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    row=db.scalar(select(CycleProfile).where(CycleProfile.owner_id==user.id))
    return row.data if row else {}

@app.put("/api/cycle/profile")
def save_cycle_profile(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    allowed={"age","height_cm","weight_kg","acne","excess_hair","weight_gain","hormonal_contraception","family_history","LH_FSH_ratio","AMH","follicle_count","scan","amh_level","lh_level","life_stage","hemoglobin","diet"}
    data={k:v for k,v in body.items() if k in allowed}
    try: validated=CycleProfileIn(**data).model_dump()
    except Exception as e: raise HTTPException(status_code=422, detail=str(e))
    if validated.get("life_stage") not in (None,"reproductive","pregnant","postpartum","midlife"): raise HTTPException(status_code=422, detail="Invalid life stage.")
    if validated.get("scan") not in (None,"polycystic","normal") or validated.get("amh_level") not in (None,"high","normal") or validated.get("lh_level") not in (None,"high","normal") or validated.get("diet") not in (None,"nonveg","veg","vegan"): raise HTTPException(status_code=422, detail="Invalid profile choice.")
    row=db.scalar(select(CycleProfile).where(CycleProfile.owner_id==user.id))
    if row is None: row=CycleProfile(owner_id=user.id,data=validated); db.add(row)
    else: row.data=validated
    db.commit(); return validated

@app.get("/api/cycle/analyze")
def analyze_cycle(db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile_row=db.scalar(select(CycleProfile).where(CycleProfile.owner_id==user.id))
    profile=dict(profile_row.data) if profile_row else {}
    rows=db.scalars(select(CycleDay).where(CycleDay.owner_id==user.id).order_by(CycleDay.recorded_on)).all()
    logs=[{"date":r.recorded_on.isoformat(),"flow":r.flow,"pain":r.pain,"mood":r.mood,"energy":r.energy,"tags":r.tags or []} for r in rows]
    try:
        result=cycle_insights.analyze(profile,logs,date.today(),get_cycle_bundle())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Screening could not be calculated. Please try again later.") from e

@app.post("/api/cycle/quick")
def quick_cycle_screen(body: QuickCycleIn, user: User = Depends(current_user)):
    try:
        return cycle_insights.quick(body.model_dump(exclude_none=True), get_cycle_bundle())
    except Exception as e:
        raise HTTPException(status_code=500, detail="Quick screening could not be calculated.") from e

@app.get("/api/resources")
def resources(topic: str | None = None):
    items = RESOURCES if not topic else [r for r in RESOURCES if topic.lower() in (r["topic"] + " " + r["title"] + " " + r["summary"]).lower()]
    return {"items":items, "notice":"Starting resource list. Verify each link and review date before public release."}

@app.get("/api/export")
def export_data(db: Session = Depends(get_db), user: User = Depends(current_user)):
    entries = list(db.scalars(select(SymptomEntry).where(SymptomEntry.owner_id == user.id).order_by(SymptomEntry.recorded_on)).all())
    cycle_days = list(db.scalars(select(CycleDay).where(CycleDay.owner_id == user.id).order_by(CycleDay.recorded_on)).all())
    cycle_profile = db.scalar(select(CycleProfile).where(CycleProfile.owner_id == user.id))
    payload = {"exported_on":date.today().isoformat(), "user":{"name":user.name,"email":user.email}, "notice":"Personal record export. Store it securely.", "symptoms":[{"symptom":e.symptom,"recorded_on":e.recorded_on.isoformat(),"severity":e.severity,"duration_hours":e.duration_hours,"description":e.description,"sleep_quality":e.sleep_quality,"sleep_hours":e.sleep_hours,"mood":e.mood,"tags":e.tags,"cycle_day":e.cycle_day} for e in entries], "cycle_profile":cycle_profile.data if cycle_profile else {}, "cycle_days":[{"recorded_on":r.recorded_on.isoformat(),"flow":r.flow,"pain":r.pain,"mood":r.mood,"energy":r.energy,"tags":r.tags,"notes":r.notes} for r in cycle_days]}
    return Response(content=json.dumps(payload, indent=2), media_type="application/json", headers={"Content-Disposition":"attachment; filename=herhealth-personal-data.json"})

@app.delete("/api/account/data", status_code=200)
def delete_all_health_data(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.query(SymptomEntry).filter(SymptomEntry.owner_id == user.id).delete(synchronize_session=False)
    db.query(CycleDay).filter(CycleDay.owner_id == user.id).delete(synchronize_session=False)
    db.query(CycleProfile).filter(CycleProfile.owner_id == user.id).delete(synchronize_session=False)
    db.commit()
    return {"message":"Your symptom and cycle records have been deleted."}

@app.delete("/api/account", status_code=200)
def delete_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(user); db.commit()
    return {"message":"Your account and associated symptom records have been deleted."}

@app.post("/api/reports/pdf")
def create_report(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    start = date.fromisoformat(body["start"]) if body.get("start") else date.min
    end = date.fromisoformat(body["end"]) if body.get("end") else date.max
    entries = list(db.scalars(select(SymptomEntry).where(SymptomEntry.owner_id == user.id, SymptomEntry.recorded_on >= start, SymptomEntry.recorded_on <= end).order_by(SymptomEntry.recorded_on)).all())
    cycle_days = list(db.scalars(select(CycleDay).where(CycleDay.owner_id == user.id, CycleDay.recorded_on >= start, CycleDay.recorded_on <= end).order_by(CycleDay.recorded_on)).all())
    selected = set(body.get("sections", ["entries", "observations", "questions"]))
    buffer = io.BytesIO(); pdf = canvas.Canvas(buffer, pagesize=letter); width, height = letter
    y = height - 54
    def line(text, font="Helvetica", size=10, leading=15):
        nonlocal y
        pdf.setFont(font, size)
        words = str(text).split(); current = ""
        for word in words:
            test = (current + " " + word).strip()
            if pdf.stringWidth(test, font, size) > width - 100:
                pdf.drawString(50, y, current); y -= leading; current = word
                if y < 60: pdf.showPage(); y = height - 54
            else: current = test
        if current: pdf.drawString(50, y, current); y -= leading
        if y < 60: pdf.showPage(); y = height - 54
    line("HerHealth Lens | Personal Health Summary", "Helvetica-Bold", 16, 22)
    line(f"Prepared for: {user.name}"); line(f"Report created: {date.today().isoformat()}")
    line(f"Selected period: {start.isoformat() if start != date.min else 'All records'} to {end.isoformat() if end != date.max else 'All records'}")
    line("This is a user-generated record summary, not a diagnosis or medical advice.", "Helvetica-Bold", 9, 18)
    if "entries" in selected:
        line("Symptom records", "Helvetica-Bold", 12, 18)
        if not entries: line("No symptom records were found in this date range.")
        for e in entries:
            line(f"{e.recorded_on.isoformat()} | {e.symptom} | Severity {e.severity}/10" + (f" | Duration {e.duration_hours} hours" if e.duration_hours is not None else ""))
            if e.description: line(f"Notes: {e.description}", size=9)
    if "observations" in selected:
        data = build_insights(entries)
        line("Descriptive observations", "Helvetica-Bold", 12, 18)
        for item in data["observations"]: line(item["text"]); line("Basis: " + item["basis"], size=8)
    if "questions" in selected:
        line("Questions to consider discussing with a healthcare professional", "Helvetica-Bold", 12, 18)
        for q in ["Which details in this symptom history are most relevant?", "Are any patterns or changes worth assessing further?", "What symptoms should prompt urgent medical attention?"]:
            line("• " + q)
    if cycle_days and "cycles" in selected:
        line("Cycle and bleeding log", "Helvetica-Bold", 12, 18)
        bleed_dates = [r.recorded_on for r in cycle_days if r.flow >= 2]
        starts = [d for i,d in enumerate(bleed_dates) if not i or (d-bleed_dates[i-1]).days > 7]
        intervals = [(b-a).days for a,b in zip(starts,starts[1:]) if 10 <= (b-a).days <= 200]
        if intervals: line(f"Mean interval between recorded bleeding days in this report: {sum(intervals)/len(intervals):.1f} days. This is descriptive, not a forecast.")
        for r in cycle_days:
            line(f"{r.recorded_on.isoformat()} | flow {r.flow}/4" + (f" | pain {r.pain}/10" if r.pain is not None else "") + (f" | symptoms: {', '.join(r.tags or [])}" if r.tags else ""))
            if r.notes: line("Notes: " + r.notes, size=9)
    line("Privacy note: This report may contain sensitive information. Store and share it carefully.", size=8)
    pdf.save(); buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition":"attachment; filename=herhealth-summary.pdf"})

# Serve the bundled production build when present; Vite remains the local development server.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
