import hmac
import secrets
from urllib.parse import urlparse

import httpx

from ..core.config import settings


TERMINAL = {"done", "failed", "timed-out"}


def pulse_group_id(user_id: str) -> str:
    """A longitudinal group represents exactly one subject.
    Derive the group id from the user id, so we cannot
    accidentally register two members' recordings into the same group."""
    return f"user-{user_id}"

class PulseClient:
    def __init__(self):
        self.s = settings()
        self.headers = {"X-Account-ID": self.s.amplifier_account_id, "X-API-Key": self.s.amplifier_api_key}

    async def wait_until_active(self) -> None:
        """Replaced by the stream's pause gate for live check-ins."""

    @property
    def enabled(self) -> bool:
        return bool(self.s.amplifier_account_id and self.s.amplifier_api_key)

    async def submit(self, group_id: str, wav_bytes: bytes, recorded_at: str) -> dict:
        """Submit into `group_id`'s longitudinal history using pulse — `POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`. 
        The completed result's `result.signals[]` carries `baseline_score`,
        `deviation_from_baseline`, `anomaly`, `z_score`, and `population_z` once the
        subject's group has enough spaced readings; they are `null` before that.
        `group_id` must be per-subject (see `pulse_group_id`). `recorded_at` (ISO 8601)
        orders this reading within that subject's history."""
        if not self.enabled:
            return {"job_id": f"mock-{secrets.token_hex(12)}", "status": "done", "result": {"summary": {"recommended_action": "inconclusive"}, "signals": [], "audio_quality": {"issues": []}, "extended_metrics": {}}}
        webhook_url = self.validate_webhook()
        async with httpx.AsyncClient(timeout=60) as client:
            await self.wait_until_active()
            upload = (await client.post(f"{self.s.amplifier_base_url}/v2/audio/uploads", headers=self.headers, json={"content_type": "audio/wav"})).raise_for_status().json()
            await self.wait_until_active()
            (await client.put(upload["upload_url"], content=wav_bytes, headers=upload.get("required_headers", {}))).raise_for_status()
            await self.wait_until_active()
            response = await client.post(
                f"{self.s.amplifier_base_url}/v2/models/pulse/groups/{group_id}/analyze/longitudinal",
                headers=self.headers,
                data={"audio_upload_ref": upload["upload_ref"], "diarize": "false", "recorded_at": recorded_at,
                      "webhook_url": webhook_url, "webhook_secret_key": self.s.amplifier_webhook_secret},
            )
            return response.raise_for_status().json()

    def validate_webhook(self) -> str:
        url = urlparse(self.s.webhook_base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in {"", "/"}
                or url.hostname in {"localhost", "127.0.0.1", "::1"}
                or not self.s.amplifier_webhook_secret):
            raise ValueError("Real AMPLIFIER analysis requires an HTTPS WEBHOOK_BASE_URL and AMPLIFIER_WEBHOOK_SECRET.")
        return self.s.webhook_base_url.rstrip("/") + "/v1/webhooks/amplifier"

    async def get_result_once(self, job_id: str) -> dict:
        """Only called by the explicit, authenticated recovery action; never scheduled."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.s.amplifier_base_url}/v2/jobs/{job_id}", headers=self.headers)
            return response.raise_for_status().json()

    @staticmethod
    def valid_signature(raw: bytes, signature: str | None) -> bool:
        return valid_signature(raw, signature)


def valid_signature(raw: bytes, signature: str | None) -> bool:
    secret = settings().amplifier_webhook_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw, "sha256").hexdigest()
    return bool(signature and signature.isascii() and hmac.compare_digest(expected, signature))


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
