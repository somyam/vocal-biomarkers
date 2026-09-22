"""Small authenticated API for the vocal-biomarkers prototype."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

from .amplifier import PulseClient
from .auth import consume_stream_ticket, mint_stream_ticket, require_user
from .config import settings
from .database import Base, SessionLocal, engine
from .models import AmplifierJob, CheckIn, Intervention, Recording, User, UserIntervention
from .streaming import apply_job_result, streams


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_INTERVENTIONS = {
    "hydrate": "Drink a glass of water before coffee.",
    "liposomal-glutathione": "Complete your morning glutathione protocol.",
    "morning-light": "Spend time in natural morning light.",
    "morning-checkin": "Find a quiet space and record a one-minute Morning Check-in.",
    "meditation": "Take ten quiet minutes to meditate.",
    "cold-plunge": "Complete your planned cold-plunge clinic visit.",
    "workout": "Complete your planned workout.",
}


def seed_prototype_data() -> None:
    with SessionLocal() as db:
        if not db.get(User, "mvp-user"):
            db.add(User(user_id="mvp-user", member=True))
        for intervention_id, guide_text in DEFAULT_INTERVENTIONS.items():
            if not db.get(Intervention, intervention_id):
                db.add(Intervention(intervention_id=intervention_id, guide_text=guide_text))
            active_link = db.scalar(select(UserIntervention).where(
                UserIntervention.user_id == "mvp-user",
                UserIntervention.intervention_id == intervention_id,
                UserIntervention.active.is_(True),
            ))
            if active_link is None:
                db.add(UserIntervention(user_id="mvp-user", intervention_id=intervention_id, active=True))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_prototype_data()
    yield


app = FastAPI(title="Vocal Biomarkers API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=[item.strip() for item in settings().cors_origin.split(",") if item.strip()],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class UserInterventionUpdate(BaseModel):
    active: bool


def checkin_payload(checkin: CheckIn) -> dict[str, Any]:
    return {"checkin_id": checkin.checkin_id, "user_id": checkin.user_id,
        "completed_at": checkin.completed_at, "duration_seconds": checkin.duration_seconds,
        "pulse_json": checkin.pulse_json}


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


@app.get("/v1/interventions")
def list_interventions(_: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        entries = list(db.scalars(select(Intervention).order_by(Intervention.intervention_id)))
        return {"items": [{"intervention_id": item.intervention_id, "guide_text": item.guide_text} for item in entries]}


@app.get("/v1/user-interventions")
def list_user_interventions(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        links = list(db.scalars(select(UserIntervention).where(
            UserIntervention.user_id == user_id,
        ).order_by(UserIntervention.started_at.desc())))
        interventions = {item.intervention_id: item for item in db.scalars(select(Intervention))}
        return {"items": [{
            "user_intervention_id": link.user_intervention_id,
            "intervention_id": link.intervention_id,
            "guide_text": interventions[link.intervention_id].guide_text,
            "active": link.active,
            "started_at": link.started_at,
            "ended_at": link.ended_at,
        } for link in links]}


@app.patch("/v1/user-interventions/{user_intervention_id}")
def update_user_intervention(user_intervention_id: str, payload: UserInterventionUpdate,
                             user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        link = db.get(UserIntervention, user_intervention_id)
        if link is None or link.user_id != user_id:
            raise HTTPException(status_code=404, detail="User intervention not found")
        link.active = payload.active
        link.ended_at = None if payload.active else utcnow()
        db.commit()
        return {"user_intervention_id": link.user_intervention_id, "active": link.active,
                "started_at": link.started_at, "ended_at": link.ended_at}


@app.post("/v1/checkins", status_code=201)
def create_checkin(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        checkin = CheckIn(user_id=user_id)
        db.add(checkin)
        db.commit()
        db.refresh(checkin)
        ticket = mint_stream_ticket(checkin.checkin_id, user_id)
        return {"checkin": checkin_payload(checkin), "stream_ticket": ticket,
            "stream_path": f"/v1/checkins/{checkin.checkin_id}/stream?ticket={ticket}"}


@app.websocket("/v1/checkins/{checkin_id}/stream")
async def stream_checkin(websocket: WebSocket, checkin_id: str, ticket: str) -> None:
    user_id = consume_stream_ticket(ticket, checkin_id)
    if user_id is None:
        await websocket.close(code=4401, reason="Invalid or expired stream ticket")
        return
    if require_owned_checkin(checkin_id, user_id) is None:
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
            if message.get("text") is None:
                continue
            try:
                action = json.loads(message["text"]).get("type")
            except json.JSONDecodeError:
                await session.emit("error", code="invalid_control", message="Control messages must be JSON.")
                continue
            if action == "checkin.start":
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
    if checkin.completed_at is None:
        await streams.finalize(checkin_id)
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@app.get("/v1/checkins/{checkin_id}")
def get_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@app.get("/v1/checkins")
def list_checkins(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        records = list(db.scalars(select(CheckIn).where(CheckIn.user_id == user_id)))
        return {"items": [checkin_payload(record) for record in records]}


@app.get("/v1/checkins/{checkin_id}/recording")
def get_recording(checkin_id: str, user_id: str = Depends(require_user)) -> Response:
    require_owned_checkin(checkin_id, user_id)
    with SessionLocal() as db:
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording is not available")
        return Response(recording.audio_wav, media_type="audio/wav")


@app.post("/v1/webhooks/amplifier")
async def amplifier_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    if not PulseClient.valid_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = json.loads(raw)
    job_id = str(payload.get("job_id") or payload.get("id") or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    return {"accepted": await apply_job_result(job_id, payload)}
