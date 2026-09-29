from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..core.auth import require_user
from ..core.database import SessionLocal
from ..models import CheckInSignal

router = APIRouter(tags=["signals"])


@router.get("/v1/signals")
def list_signals(user_id: str = Depends(require_user)) -> dict[str, Any]:
    with SessionLocal() as db:
        rows = list(db.scalars(select(CheckInSignal).where(
            CheckInSignal.user_id == user_id,
        ).order_by(CheckInSignal.recorded_at)))
        return {"items": [{
            "signal_name": row.signal_name,
            "recorded_at": row.recorded_at,
            "score": row.score,
            "level": row.level,
            "flagged": row.flagged,
            "latest_score": row.latest_score,
            "baseline_score": row.baseline_score,
            "deviation_from_baseline": row.deviation_from_baseline,
            "anomaly": row.anomaly,
            "z_score": row.z_score,
            "population_z": row.population_z,
        } for row in rows]}
