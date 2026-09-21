import asyncio
import hmac
import secrets

import httpx

from .config import settings


TERMINAL = {"done", "failed", "timed-out"}


class PulseClient:
    def __init__(self):
        self.s = settings()
        self.headers = {"X-Account-ID": self.s.amplifier_account_id, "X-API-Key": self.s.amplifier_api_key}

    @property
    def enabled(self) -> bool:
        return bool(self.s.amplifier_account_id and self.s.amplifier_api_key)

    async def submit(self, wav_bytes: bytes) -> dict:
        if not self.enabled:
            return {"job_id": f"mock-{secrets.token_hex(12)}", "status": "done", "result": {"summary": {"recommended_action": "inconclusive"}, "signals": [], "audio_quality": {"issues": []}, "extended_metrics": {}}}
        async with httpx.AsyncClient(timeout=60) as client:
            upload = (await client.post(f"{self.s.amplifier_base_url}/v2/audio/uploads", headers=self.headers, json={"content_type": "audio/wav"})).raise_for_status().json()
            (await client.put(upload["upload_url"], content=wav_bytes, headers=upload.get("required_headers", {}))).raise_for_status()
            response = await client.post(f"{self.s.amplifier_base_url}/v2/models/pulse/analyze", headers=self.headers, data={"audio_upload_ref": upload["upload_ref"], "diarize": "false"})
            return response.raise_for_status().json()

    async def wait_for_result(self, job_id: str) -> dict:
        if job_id.startswith("mock-"):
            return {"job_id": job_id, "status": "done", "result": {"summary": {"recommended_action": "inconclusive"}, "signals": [], "audio_quality": {"issues": []}, "extended_metrics": {}}}
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                payload = (await client.get(f"{self.s.amplifier_base_url}/v2/jobs/{job_id}", headers=self.headers)).raise_for_status().json()
                if str(payload.get("status", "")).lower() in TERMINAL:
                    return payload
                await asyncio.sleep(self.s.pulse_poll_seconds)

    @staticmethod
    def valid_signature(raw: bytes, signature: str | None) -> bool:
        return valid_signature(raw, signature)


def valid_signature(raw: bytes, signature: str | None) -> bool:
    secret = settings().amplifier_webhook_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw, "sha256").hexdigest()
    return bool(signature and hmac.compare_digest(expected, signature))


def quality_view(result: dict | list[dict]) -> dict:
    responses = result if isinstance(result, list) else [result]
    issues = []
    for response in responses:
        payload = response.get("result", response)
        issues.extend(((payload.get("audio_quality") or {}).get("issues") or []))
    rerecord = any(issue in {"poor_voice_quality", "insufficient_speech", "high_background_noise", "invalid_speaker"} for issue in issues)
    return {"status": "needs_rerecord" if rerecord else "clear", "issues": issues}


def trend_view(results: list[dict]) -> dict:
    if not results:
        return {"status": "pending", "message": "Your check-in is still being processed."}
    if any(quality_view(result)["status"] == "needs_rerecord" for result in results):
        return {"status": "needs-recording", "message": "A clearer recording will make your trends more useful."}
    return {"status": "baseline", "message": "This check-in has been added to your personal wellness baseline."}
