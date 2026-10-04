import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.amplifier import PulseClient
from app.services.streaming import StreamSession


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_after", ["upload", "put"])
async def test_pause_gates_upload_steps_without_status_requests(monkeypatch, pause_after):
    stream = StreamSession(checkin_id="test", user_id="test")
    await stream.start()
    paused = asyncio.Event()
    calls = []
    polls = 0

    async def transport(request):
        nonlocal polls
        if request.url.path == "/v2/audio/uploads":
            stage = "upload"
            payload = {"upload_url": "https://upload.test/audio", "upload_ref": "ref"}
        elif request.method == "PUT":
            stage, payload = "put", {}
        elif request.method == "POST":
            from urllib.parse import parse_qs
            data = parse_qs(request.content.decode())
            assert data['webhook_url'] == ['https://callback.example.test/v1/webhooks/amplifier']
            assert data['webhook_secret_key'] == ['test-secret']
            stage, payload = "analyze", {"job_id": "job-test", "status": "queued"}
        else:
            polls += 1
            stage = "poll"
            payload = {"job_id": "job-test", "status": "processing" if polls == 1 else "done"}
        calls.append(stage)
        if stage == pause_after and not paused.is_set():
            await stream.pause()
            paused.set()
        return httpx.Response(200, json=payload)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(transport), **kwargs))
    monkeypatch.setattr(settings(), "amplifier_account_id", "test-only")
    monkeypatch.setattr(settings(), "amplifier_api_key", "test-only")
    monkeypatch.setattr(settings(), "webhook_base_url", "https://callback.example.test")
    monkeypatch.setattr(settings(), "amplifier_webhook_secret", "test-secret")
    pulse = PulseClient()
    pulse.wait_until_active = stream.wait_until_active

    async def analyze():
        submission = await pulse.submit("test", b"wav", "2026-10-04T00:00:00Z")
        return submission

    task = asyncio.create_task(analyze())
    try:
        await asyncio.wait_for(paused.wait(), 1)
        calls_at_pause = list(calls)
        await asyncio.sleep(0.02)
        assert calls == calls_at_pause
        assert not task.done()
        await stream.resume()
        assert (await asyncio.wait_for(task, 1))["status"] == "queued"
        assert calls == ["upload", "put", "analyze"]
    finally:
        task.cancel()
        stream.partial_loop_task.cancel()
        await asyncio.gather(task, stream.partial_loop_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_submission_requires_callback_before_any_upload(monkeypatch):
    monkeypatch.setattr(settings(), 'amplifier_account_id', 'test-only')
    monkeypatch.setattr(settings(), 'amplifier_api_key', 'test-only')
    monkeypatch.setattr(settings(), 'webhook_base_url', '')
    with pytest.raises(ValueError, match='WEBHOOK_BASE_URL'):
        await PulseClient().submit('user', b'wav', '2026-10-04T00:00:00Z')
