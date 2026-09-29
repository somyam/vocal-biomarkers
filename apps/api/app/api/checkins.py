from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from ..core.auth import mint_stream_ticket, require_user
from ..core.database import SessionLocal
from ..models import CheckIn, Recording
from ..services.streaming import streams

router = APIRouter(prefix="/v1/checkins", tags=["checkins"])


def checkin_payload(checkin: CheckIn) -> dict[str, Any]:
    return {"checkin_id": checkin.checkin_id, "user_id": checkin.user_id,
        "started_at": checkin.started_at, "completed_at": checkin.completed_at,
        "duration_seconds": checkin.duration_seconds, "pulse_json": checkin.pulse_json,
        "transcript": checkin.transcript}


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
    if checkin.completed_at is None:
        await streams.finalize(checkin_id)
    return checkin_payload(require_owned_checkin(checkin_id, user_id))


@router.get("/{checkin_id}")
def get_checkin(checkin_id: str, user_id: str = Depends(require_user)) -> dict[str, Any]:
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
