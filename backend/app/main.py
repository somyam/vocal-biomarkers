"""Authenticated API for the Vocal Biomarkers MVP."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from .amplifier import PulseClient
from .auth import consume_stream_ticket, mint_stream_ticket, require_user
from .config import settings
from .database import Base, SessionLocal, engine
from .models import CheckIn, Habit, HabitCompletion, Recording, ReminderSetting
from .streaming import apply_job_result, streams


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_HABITS = [
    ("Hydrate", "daily"), ("Liposomal Glutathione", "daily"), ("Morning Light", "daily"),
    ("Morning Check-in", "daily"), ("Meditation", "daily"),
    ("Clinic Visit — Cold Plunge", "weekly"), ("Workout", "daily"),
]


def seed_mvp_data() -> None:
    with SessionLocal() as db:
        if not db.scalar(select(Habit.id).limit(1)):
            db.add_all([Habit(name=name, frequency=frequency) for name, frequency in DEFAULT_HABITS])
        if not db.get(ReminderSetting, "mvp-user"):
            db.add(ReminderSetting(user_id="mvp-user", time_local="08:00", enabled=True))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_mvp_data()
    yield


app = FastAPI(title="Vocal Biomarkers API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=[item.strip() for item in settings().cors_origin.split(",") if item.strip()],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class CheckinCreate(BaseModel):
    source: str = "morning-check-in"


class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    frequency: Literal["daily", "weekly", "custom"] = "daily"


class HabitUpdate(BaseModel):
    frequency: Literal["daily", "weekly", "custom"] | None = None
    active: bool | None = None


class ReminderUpdate(BaseModel):
    time_local: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True


def checkin_payload(checkin: CheckIn) -> dict[str, Any]:
    return {"id": checkin.id, "status": checkin.status, "created_at": checkin.created_at,
        "started_at": checkin.started_at, "finished_at": checkin.finished_at,
        "completed_at": checkin.completed_at, "duration_seconds": checkin.duration_seconds,
        "quality": checkin.quality_result, "summary": checkin.pulse_summary,
        "trend": checkin.trend_summary}


def require_owned_checkin(checkin_id: str, user_id: str) -> CheckIn:
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None or checkin.user_id != user_id:
            raise HTTPException(status_code=404, detail="Check-in not found")
        db.expunge(checkin)
        return checkin


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/checkins", status_code=201)
def create_checkin(_: CheckinCreate, user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        checkin = CheckIn(user_id=user_id, status="created")
        db.add(checkin)
        db.commit()
        db.refresh(checkin)
        ticket = mint_stream_ticket(checkin.id, user_id)
        return {"checkin": checkin_payload(checkin), "stream_ticket": ticket,
            "stream_path": f"/v1/checkins/{checkin.id}/stream?ticket={ticket}"}


@app.websocket("/v1/checkins/{checkin_id}/stream")
async def stream_checkin(websocket: WebSocket, checkin_id: str, ticket: str) -> None:
    user_id = consume_stream_ticket(ticket, checkin_id)
    if user_id is None:
        await websocket.close(code=4401, reason="Invalid or expired stream ticket")
        return
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None or checkin.user_id != user_id:
            await websocket.close(code=4404, reason="Check-in not found")
            return
    await websocket.accept()
    session = streams.create(checkin_id, user_id, websocket)
    await session.emit("connected", sample_rate=16000, encoding="pcm_s16le", window_seconds=30)
    try:
        while True:
            message = await websocket.receive()
            if message.get("bytes") is not None:
                await session.ingest(message["bytes"])
                continue
            raw = message.get("text")
            if raw is None:
                continue
            try:
                control = json.loads(raw)
            except json.JSONDecodeError:
                await session.emit("error", code="invalid_control", message="Control messages must be JSON.")
                continue
            action = control.get("type")
            if action == "checkin.start":
                if control.get("sample_rate", 16000) != 16000 or control.get("encoding", "pcm_s16le") != "pcm_s16le":
                    await session.emit("error", code="unsupported_audio", message="Use 16 kHz mono signed-16-bit PCM audio.")
                else:
                    await session.start()
            elif action == "checkin.pause":
                await session.pause()
            elif action == "checkin.resume":
                await session.resume()
            elif action == "checkin.end":
                await session.finalize()
                break
            else:
                await session.emit("error", code="unknown_control", message="Unknown check-in control frame.")
    except WebSocketDisconnect:
        pass
    finally:
        if session.finalized:
            streams.remove(checkin_id)


@app.post("/v1/checkins/{checkin_id}/finish")
async def finish_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
    checkin = require_owned_checkin(checkin_id, user_id)
    if checkin.status in {"created", "recording"}:
        await streams.finalize(checkin_id)
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@app.get("/v1/checkins/{checkin_id}")
def get_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@app.get("/v1/checkins")
def list_checkins(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        records = list(db.scalars(select(CheckIn).where(CheckIn.user_id == user_id).order_by(CheckIn.created_at.desc())))
        return {"items": [checkin_payload(item) for item in records]}


@app.get("/v1/checkins/{checkin_id}/recording")
def get_recording(checkin_id: str, user_id: str = Depends(require_user)) -> Response:
    require_owned_checkin(checkin_id, user_id)
    with SessionLocal() as db:
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording is not available")
        return Response(recording.wav_bytes, media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=morning-checkin.wav"})


@app.get("/v1/trends")
def trends(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        checkins = list(db.scalars(select(CheckIn).where(CheckIn.user_id == user_id,
            CheckIn.status == "complete").order_by(CheckIn.completed_at.desc())))
        return {"checkins_analyzed": len(checkins),
            "latest": checkin_payload(checkins[0]) if checkins else None,
            "summaries": [item.trend_summary for item in checkins[:12] if item.trend_summary]}


@app.get("/v1/habits")
def list_habits(_: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        habits = list(db.scalars(select(Habit).order_by(Habit.created_at)))
        return {"items": [{"id": h.id, "name": h.name, "frequency": h.frequency, "active": h.active} for h in habits]}


@app.post("/v1/habits", status_code=201)
def create_habit(payload: HabitCreate, _: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        habit = Habit(name=payload.name, frequency=payload.frequency)
        db.add(habit); db.commit(); db.refresh(habit)
        return {"id": habit.id, "name": habit.name, "frequency": habit.frequency, "active": habit.active}


@app.patch("/v1/habits/{habit_id}")
def update_habit(habit_id: str, payload: HabitUpdate, _: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        habit = db.get(Habit, habit_id)
        if habit is None:
            raise HTTPException(status_code=404, detail="Habit not found")
        if payload.frequency is not None: habit.frequency = payload.frequency
        if payload.active is not None: habit.active = payload.active
        db.commit()
        return {"id": habit.id, "name": habit.name, "frequency": habit.frequency, "active": habit.active}


@app.post("/v1/habits/{habit_id}/completions", status_code=201)
def complete_habit(habit_id: str, _: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        habit = db.get(Habit, habit_id)
        if habit is None:
            raise HTTPException(status_code=404, detail="Habit not found")
        completion = HabitCompletion(habit_id=habit_id, habit_name=habit.name)
        db.add(completion); db.commit()
        return {"id": completion.id, "habit_id": habit_id, "completed_at": completion.completed_at}


@app.get("/v1/reminder")
def get_reminder(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        reminder = db.get(ReminderSetting, user_id)
        if reminder is None:
            reminder = ReminderSetting(user_id=user_id)
            db.add(reminder); db.commit()
        return {"time_local": reminder.time_local, "enabled": reminder.enabled}


@app.put("/v1/reminder")
def update_reminder(payload: ReminderUpdate, user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        reminder = db.get(ReminderSetting, user_id) or ReminderSetting(user_id=user_id)
        reminder.time_local, reminder.enabled = payload.time_local, payload.enabled
        db.add(reminder); db.commit()
        return {"time_local": reminder.time_local, "enabled": reminder.enabled}


@app.post("/v1/webhooks/amplifier")
async def amplifier_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    if not PulseClient.valid_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    job_id = str(payload.get("job_id") or payload.get("id") or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    return {"accepted": await apply_job_result(job_id, payload)}
