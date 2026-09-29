from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..core.auth import require_user
from ..core.database import SessionLocal
from ..models import Intervention, UserIntervention

router = APIRouter(tags=["interventions"])


class UserInterventionUpdate(BaseModel):
    active: bool


@router.get("/v1/interventions")
def list_interventions(_: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        entries = list(db.scalars(select(Intervention).order_by(Intervention.intervention_id)))
        return {"items": [{"intervention_id": item.intervention_id, "guide_text": item.guide_text} for item in entries]}


@router.get("/v1/user-interventions")
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


@router.patch("/v1/user-interventions/{user_intervention_id}")
def update_user_intervention(user_intervention_id: str, payload: UserInterventionUpdate,
                             user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        link = db.get(UserIntervention, user_intervention_id)
        if link is None or link.user_id != user_id:
            raise HTTPException(status_code=404, detail="User intervention not found")
        link.active = payload.active
        link.ended_at = None if payload.active else datetime.now(timezone.utc)
        db.commit()
        return {"user_intervention_id": link.user_intervention_id, "active": link.active,
                "started_at": link.started_at, "ended_at": link.ended_at}
