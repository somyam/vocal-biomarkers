from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from ..services.amplifier import PulseClient
from ..services.streaming import apply_job_result

router = APIRouter(tags=["webhooks"])


@router.post("/v1/webhooks/amplifier")
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
