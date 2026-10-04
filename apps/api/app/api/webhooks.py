from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException, Request

from ..services.amplifier import PulseClient, TERMINAL
from ..services.analysis import receive_result

router = APIRouter(tags=['webhooks'])


def validate_job_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected a job object')
    job_id = payload.get('job_id') or payload.get('id')
    if not isinstance(job_id, str) or not job_id or len(job_id) > 128:
        raise ValueError('Invalid job_id')
    if payload.get('status') not in TERMINAL:
        raise ValueError('Expected a terminal job status')
    result = payload.get('result')
    if result is not None:
        if not isinstance(result, dict) or not isinstance(result.get('signals', []), list):
            raise ValueError('Invalid result')
        for signal in result.get('signals', []):
            if not isinstance(signal, dict) or not isinstance(signal.get('name'), str) or not signal['name'] or len(signal['name']) > 64:
                raise ValueError('Invalid signal name')
            if not isinstance(signal.get('level', ''), str) or len(signal.get('level', '')) > 24:
                raise ValueError('Invalid signal level')
            for key in ['flagged', 'anomaly']:
                if signal.get(key) is not None and not isinstance(signal[key], bool):
                    raise ValueError('Invalid signal boolean')
            for key in ['score', 'latest_score', 'baseline_score', 'deviation_from_baseline', 'z_score', 'population_z']:
                if signal.get(key) is not None and not math.isfinite(float(signal[key])):
                    raise ValueError('Invalid signal value')
    return job_id


@router.post('/v1/webhooks/amplifier')
async def amplifier_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    if not PulseClient.valid_signature(raw, request.headers.get('X-Webhook-Signature', '')):
        raise HTTPException(401, 'Invalid webhook signature')
    try:
        payload = json.loads(raw)
        job_id = validate_job_payload(payload)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, 'Invalid terminal job payload')
    applied = await receive_result(job_id, payload)
    # Valid unknown/duplicate jobs are durably acknowledged, avoiding needless
    # provider retries; DB failures propagate as 5xx so the provider can retry.
    return {'accepted': True, 'applied': applied}
