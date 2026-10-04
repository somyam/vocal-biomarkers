import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.amplifier import PulseClient
from app.services.streaming import StreamSession


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_after", ["upload", "put", "analyze", "poll"])
async def test_pause_gates_every_upload_and_poll_request(monkeypatch, pause_after):
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
    monkeypatch.setattr(settings(), "pulse_poll_seconds", 0.001)
    pulse = PulseClient()
    pulse.wait_until_active = stream.wait_until_active

    async def analyze():
        submission = await pulse.submit("test", b"wav", "2026-10-04T00:00:00Z")
        return await pulse.wait_for_result(submission["job_id"])

    task = asyncio.create_task(analyze())
    try:
        await asyncio.wait_for(paused.wait(), 1)
        calls_at_pause = list(calls)
        await asyncio.sleep(0.02)
        assert calls == calls_at_pause
        assert not task.done()
        await stream.resume()
        assert (await asyncio.wait_for(task, 1))["status"] == "done"
        assert calls == ["upload", "put", "analyze", "poll", "poll"]
    finally:
        task.cancel()
        stream.partial_loop_task.cancel()
        await asyncio.gather(task, stream.partial_loop_task, return_exceptions=True)
