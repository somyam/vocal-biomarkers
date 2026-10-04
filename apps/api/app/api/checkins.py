from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from ..core.auth import mint_stream_ticket, require_user
from ..core.database import SessionLocal
from ..models import AmplifierJob, CheckIn, ConversationTurn, Recording
from ..services.streaming import streams
from ..services.analysis import analysis_status, receive_result
from ..services.amplifier import PulseClient, TERMINAL
from ..services.conversation import conversation_messages, reply_to_text, text_turn_lock

router = APIRouter(prefix="/v1/checkins", tags=["checkins"])


def checkin_payload(checkin: CheckIn) -> dict[str, Any]:
    with SessionLocal() as db:
        turns = list(db.scalars(select(ConversationTurn).where(
            ConversationTurn.checkin_id == checkin.checkin_id,
        ).order_by(ConversationTurn.end_sample)))
        messages = conversation_messages(db, checkin)
        analysis = analysis_status(db, checkin.checkin_id)
    return {"checkin_id": checkin.checkin_id, "user_id": checkin.user_id,
        "started_at": checkin.started_at, "completed_at": checkin.completed_at,
        "recording_completed_at": checkin.recording_completed_at, "analysis_status": analysis,
        "duration_seconds": checkin.duration_seconds, "pulse_json": checkin.pulse_json,
        "transcript": checkin.transcript,
        "conversation_messages": messages,
        "conversation_turns": [{"turn_id": turn.turn_id, "transcript": turn.transcript,
            "reply": turn.reply, "model": turn.model, "status": turn.status, "error": turn.error,
            "usage": (turn.raw_response or {}).get("usage", {})}
            for turn in turns]}


def require_owned_checkin(checkin_id: str, user_id: str) -> CheckIn:
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None or checkin.user_id != user_id:
            raise HTTPException(status_code=404, detail="Check-in not found")
        db.expunge(checkin)
        return checkin


@router.post("", status_code=201)
def create_checkin(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        checkin = CheckIn(user_id=user_id)
        db.add(checkin)
        db.commit()
        db.refresh(checkin)
        ticket = mint_stream_ticket(checkin.checkin_id, user_id)
        return {"checkin": checkin_payload(checkin), "stream_ticket": ticket,
            "stream_path": f"/v1/checkins/{checkin.checkin_id}/stream?ticket={ticket}"}


@router.post("/{checkin_id}/finish")
async def finish_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
    checkin = require_owned_checkin(checkin_id, user_id)
    if checkin.recording_completed_at is None:
        await streams.finalize(checkin_id)
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@router.get("/{checkin_id}")
def get_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


class TextMessage(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=10000)

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


@router.post("/{checkin_id}/messages")
async def send_message(checkin_id: str, body: TextMessage, user_id: str = Depends(require_user)) -> dict[str, Any]:
    checkin = require_owned_checkin(checkin_id, user_id)
    if checkin.recording_completed_at is None:
        raise HTTPException(409, "The recording is still being saved. Please wait.")
    async with text_turn_lock(checkin_id):
        await reply_to_text(checkin_id, str(body.request_id), body.text)
        return checkin_payload(require_owned_checkin(checkin_id, user_id))


@router.get("")
def list_checkins(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        records = list(db.scalars(select(CheckIn).where(CheckIn.user_id == user_id)))
        return {"items": [checkin_payload(record) for record in records]}


@router.get("/{checkin_id}/recording")
def get_recording(checkin_id: str, user_id: str = Depends(require_user)) -> Response:
    require_owned_checkin(checkin_id, user_id)
    with SessionLocal() as db:
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording is not available")
        return Response(recording.audio_wav, media_type="audio/wav")


@router.post("/{checkin_id}/analysis/refresh")
async def refresh_analysis_once(checkin_id: str, user_id: str = Depends(require_user)):
    from .webhooks import validate_job_payload
    require_owned_checkin(checkin_id, user_id)
    stream = streams.sessions.get(checkin_id)
    if stream is not None and stream.paused:
        raise HTTPException(409, "Resume or save before checking analysis.")
    with SessionLocal() as db:
        job_ids = list(db.scalars(select(AmplifierJob.job_id).where(
            AmplifierJob.checkin_id == checkin_id, AmplifierJob.completed_at.is_(None))))
    unavailable = 0
    client = PulseClient()
    for job_id in job_ids:
        try:
            if stream is not None:
                await stream.wait_until_active()
            payload = await client.get_result_once(job_id)
            if payload.get('status') in TERMINAL:
                if validate_job_payload(payload) != job_id:
                    raise ValueError('Mismatched job ID')
                await receive_result(job_id, payload)
        except Exception:
            # A recovery request failing does not make the provider job terminal.
            unavailable += 1
    payload = checkin_payload(require_owned_checkin(checkin_id, user_id))
    return {**payload, 'analysis_refresh_errors': unavailable}
