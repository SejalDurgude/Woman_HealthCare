"""CycleLens API (FastAPI). Stateless: inputs arrive with each request and nothing is stored.

User data is analysed in memory and discarded. Request bodies are never logged by this code.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import brief
import core
import demo
import insights
import modules

app = FastAPI(title="CycleLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

if not os.path.exists(core.MODEL_PATH):
    import train
    train.main(quiet=True)
BUNDLE = core.load_bundle()


@app.middleware("http")
async def no_store(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


class Profile(BaseModel):
    age: Optional[float] = Field(None, ge=10, le=65)
    height_cm: Optional[float] = Field(None, ge=120, le=220)
    weight_kg: Optional[float] = Field(None, ge=30, le=250)
    acne: Optional[int] = Field(None, ge=0, le=1)
    excess_hair: Optional[int] = Field(None, ge=0, le=1)
    weight_gain: Optional[int] = Field(None, ge=0, le=1)
    hormonal_contraception: bool = False
    family_history: List[str] = []
    LH_FSH_ratio: Optional[float] = Field(None, ge=0.1, le=6)
    AMH: Optional[float] = Field(None, ge=0.1, le=20)
    follicle_count: Optional[float] = Field(None, ge=0, le=40)
    scan: Optional[Literal["polycystic", "normal"]] = None
    amh_level: Optional[Literal["high", "normal"]] = None
    lh_level: Optional[Literal["high", "normal"]] = None
    life_stage: Optional[Literal["reproductive", "pregnant", "postpartum", "midlife"]] = None
    hemoglobin: Optional[float] = Field(None, ge=3, le=20)      # g/dL, from a blood count
    diet: Optional[Literal["nonveg", "veg", "vegan"]] = None


class Log(BaseModel):
    date: str
    flow: int = Field(0, ge=0, le=4)
    pain: Optional[int] = Field(None, ge=0, le=10)
    mood: Optional[int] = Field(None, ge=1, le=5)
    energy: Optional[int] = Field(None, ge=1, le=5)
    tags: List[str] = []

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        dt.date.fromisoformat(v)
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        bad = [t for t in v if t not in insights.TAGS]
        if bad:
            raise ValueError(f"unknown tags {bad}")
        return v


class AnalyzeReq(BaseModel):
    profile: Profile = Profile()
    logs: List[Log] = Field([], max_length=900)
    today: Optional[str] = None


def run(req: AnalyzeReq):
    today = dt.date.fromisoformat(req.today) if req.today else dt.date.today()
    seen, logs = set(), []
    for l in reversed(req.logs):                       # last write wins per date
        if l.date not in seen:
            seen.add(l.date)
            logs.append(l.model_dump())
    profile = req.profile.model_dump()
    return profile, insights.analyze(profile, logs, today, BUNDLE)


class QuickReq(Profile):
    cycle_band: Literal["short", "normal", "long", "very_long", "absent", "unsure"] = "unsure"
    regularity: Literal["regular", "varies", "unpredictable"] = "regular"
    period_days: Literal["short", "normal", "long"] = "normal"
    flow: Literal["light", "normal", "heavy", "very_heavy"] = "normal"
    pain: int = Field(0, ge=0, le=10)
    pain_other: bool = False
    pain_sex: bool = False
    bowel_urinary: bool = False
    fatigue: bool = False
    hair_loss: bool = False
    cold: bool = False
    palpitations: bool = False
    low_mood: bool = False
    mood_before: bool = False
    dizziness: bool = False
    fainting: bool = False
    severe_pain_now: bool = False
    soaking: bool = False
    # midlife
    hot_flash: bool = False
    night_sweats: bool = False
    poor_sleep: bool = False
    brain_fog: bool = False
    vaginal_dryness: bool = False
    joint_pain: bool = False
    # anaemia
    breathless: bool = False
    pica: bool = False
    brittle_nails: bool = False
    pale: bool = False
    # pregnancy and postpartum (PHQ-2: 0 not at all, 1 several days, 2 more than half the days, 3 nearly every day)
    phq_interest: int = Field(0, ge=0, le=3)
    phq_down: int = Field(0, ge=0, le=3)
    anxiety: bool = False
    anhedonia: bool = False
    self_harm_thoughts: bool = False
    severe_headache: bool = False
    vision_changes: bool = False
    reduced_movement: bool = False
    sudden_swelling: bool = False
    fever: bool = False
    heavy_pp_bleed: bool = False


@app.post("/api/quick")
def quick(req: QuickReq):
    return insights.quick(req.model_dump(), BUNDLE)


@app.post("/api/quick/brief")
def quick_brief(req: QuickReq):
    a = insights.quick(req.model_dump(), BUNDLE)
    return Response(brief.build(req.model_dump(), a), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=cyclelens_brief.pdf"})


@app.get("/api/health")
def health():
    return {"status": "ok", "data_source": BUNDLE["data_source"]}


@app.get("/api/meta")
def meta():
    return {"tags": insights.TAGS, "red_tags": sorted(insights.RED_TAGS | modules.RED_TAGS_NEW),
            "life_stages": [{"id": k, "title": v} for k, v in modules.STAGE_TXT.items()], "data_source": BUNDLE["data_source"],
            "metrics": BUNDLE.get("metrics"), "disclaimer": core.DISCLAIMER,
            "demos": [{"id": k, "title": v["title"], "blurb": v["blurb"]} for k, v in demo.SCENARIOS.items()]}


@app.get("/api/demo/{name}")
def demo_data(name: str):
    if name not in demo.SCENARIOS:
        raise HTTPException(404, "unknown demo")
    return demo.build(name)


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    return run(req)[1]


@app.post("/api/brief")
def make_brief(req: AnalyzeReq):
    profile, analysis = run(req)
    pdf = brief.build(profile, analysis)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=cyclelens_brief.pdf"})


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "frontend", "dist")          # React build output (npm run build)

if os.path.isdir(DIST):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
else:
    @app.get("/")
    def no_build():
        return Response("CycleLens API is running, but the React app is not built yet. "
                        "Run: cd frontend && npm install && npm run build   (or npm run dev for development).",
                        media_type="text/plain")
