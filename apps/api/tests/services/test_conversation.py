import asyncio
import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.models import CheckIn, ConversationTurn, User
from app.services.conversation import ConversationError, SonnetClient
from app.services.streaming import streams


@pytest.mark.asyncio
async def test_sonnet_request_uses_server_key_and_returns_text(monkeypatch):
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "msg-test", "model": "test-sonnet",
            "content": [{"type": "text", "text": "What helped today?"}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(settings(), "anthropic_api_key", "test-server-key")
    messages = [{"role": "user", "content": "I feel better today."}]
    result = await SonnetClient().reply(messages)
    assert result["reply"] == "What helped today?"
    assert result["raw_response"]["id"] == "msg-test"
    request, = seen
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "test-server-key"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["model"] == settings().anthropic_model
    assert body["messages"] == messages
    assert body["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert "test-server-key" not in request.content.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_provider_errors_are_safe(monkeypatch, status):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"error": "secret-provider-detail"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    monkeypatch.setattr(settings(), "anthropic_api_key", "test-key")
    with pytest.raises(ConversationError) as error:
        await SonnetClient().reply([{"role": "user", "content": "Hello"}])
    assert "secret-provider-detail" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_key_does_not_fake_a_reply():
    assert settings().anthropic_api_key == ""
    with pytest.raises(ConversationError, match="not configured"):
        await SonnetClient().reply([{"role": "user", "content": "Hello"}])


def test_anthropic_api_alias(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API", "test-alias-key")
    assert Settings(_env_file=None).anthropic_api_key == "test-alias-key"


@pytest.fixture
def turn_stream():
    with SessionLocal() as db:
        user = User(user_id=str(uuid.uuid4()))
        db.add(user)
        db.commit()
        checkin = CheckIn(user_id=user.user_id)
        db.add(checkin)
        db.commit()
        stream = streams.create(checkin.checkin_id, user.user_id)
    events = []
    async def emit(event, **payload):
        events.append({"type": event, **payload})
    stream.emit = emit
    yield stream, events
    streams.remove(stream.checkin_id)


@pytest.mark.asyncio
async def test_end_turn_persists_history_and_keeps_recording_paused(turn_stream, monkeypatch):
    stream, events = turn_stream
    calls = []
    async def reply(self, messages, *, history_context=None):
        calls.append(messages)
        return {"reply": f"Reply {len(calls)}", "model": "test-sonnet", "raw_response": {
            "id": f"msg-{len(calls)}", "usage": {"cache_read_input_tokens": 512 if len(calls) == 2 else 0,
            "cache_creation_input_tokens": 512 if len(calls) == 1 else 30}}}
    monkeypatch.setattr(SonnetClient, "reply", reply)
    await stream.start()
    for _ in range(2):
        await stream.ingest(b"\0\0" * 16000)
        await stream.end_turn()
        await stream.turn_task
        assert stream.paused and not stream.finalized
        await stream.resume()
    assert len(calls) == 2
    assert calls[1] == [
        {"role": "user", "content": "[mock transcript]"},
        {"role": "assistant", "content": "Reply 1"},
        {"role": "user", "content": "[mock transcript]"},
    ]
    with SessionLocal() as db:
        turns = list(db.scalars(select(ConversationTurn).where(ConversationTurn.checkin_id == stream.checkin_id)
                               .order_by(ConversationTurn.end_sample)))
        assert [(t.start_sample, t.end_sample) for t in turns] == [(0, 16000), (16000, 32000)]
        assert [t.reply for t in turns] == ["Reply 1", "Reply 2"]
        assert all(t.completed_at and t.status == "done" for t in turns)
        assert turns[1].raw_response["usage"]["cache_read_input_tokens"] == 512
        assert turns[0].raw_response["id"] == "msg-1"
    results = [event for event in events if event["type"] == "turn_result"]
    assert results[0]["usage"]["cache_creation_input_tokens"] == 512
    assert results[1]["usage"]["cache_read_input_tokens"] == 512
    await stream.end_turn()  # No new audio, no duplicate Sonnet request.
    assert len(calls) == 2
    assert events[-1]["code"] == "conversation_failed"
    await stream.finalize()
    assert stream.processing_complete


@pytest.mark.asyncio
async def test_duplicate_end_turn_and_resume_do_not_interrupt_pending_reply(turn_stream, monkeypatch):
    stream, events = turn_stream
    gate = asyncio.Event()
    calls = []
    async def reply(self, messages, *, history_context=None):
        calls.append(messages)
        await gate.wait()
        return {"reply": "Reply", "model": "test-sonnet", "raw_response": {}}
    monkeypatch.setattr(SonnetClient, "reply", reply)
    await stream.start()
    await stream.ingest(b"\0\0" * 16000)
    await stream.end_turn()
    task = stream.turn_task
    await stream.end_turn()
    assert stream.turn_task is task
    await stream.resume()
    assert stream.paused
    gate.set()
    await task
    assert len(calls) == 1
    await stream.finalize()


@pytest.mark.asyncio
async def test_failed_turn_can_retry_without_duplicate_row(turn_stream, monkeypatch):
    stream, events = turn_stream
    calls = []
    async def reply(self, messages, *, history_context=None):
        calls.append(messages)
        if len(calls) == 1:
            raise ConversationError("Sonnet is temporarily unavailable.")
        return {"reply": "Reply", "model": "test-sonnet", "raw_response": {}}
    monkeypatch.setattr(SonnetClient, "reply", reply)
    await stream.start()
    await stream.ingest(b"\0\0" * 16000)
    await stream.end_turn()
    await stream.turn_task
    assert events[-1]["code"] == "conversation_failed"
    assert stream.turn_start_sample == 0
    await stream.end_turn()
    await stream.turn_task
    assert stream.turn_start_sample == 16000
    with SessionLocal() as db:
        turns = list(db.scalars(select(ConversationTurn).where(ConversationTurn.checkin_id == stream.checkin_id)))
        assert len(turns) == 1 and turns[0].status == "done"
    await stream.finalize()


@pytest.mark.asyncio
@pytest.mark.parametrize('tail_seconds', [0, 2])
async def test_save_preserves_turns_and_only_transcribes_remaining_speech(turn_stream, monkeypatch, tail_seconds):
    import io
    import wave
    from app.api.checkins import checkin_payload
    from app.services.transcribe import transcriber
    stream, _ = turn_stream
    durations = []
    calls = []
    async def transcribe(wav):
        with wave.open(io.BytesIO(wav)) as audio:
            duration = audio.getnframes() / audio.getframerate()
        durations.append(duration)
        return f'Speech {len(durations)} ({duration}s)'
    async def reply(self, messages, *, history_context=None):
        calls.append(messages)
        return {'reply': 'Coach reply', 'model': 'test', 'raw_response': {}}
    monkeypatch.setattr(transcriber(), 'transcribe', transcribe)
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    await stream.start()
    await stream.ingest(b'\0\0' * 16000)
    await stream.end_turn()
    await stream.turn_task
    if tail_seconds:
        await stream.resume()
        await stream.ingest(b'\0\0' * 16000 * tail_seconds)
    await stream.finalize()
    assert len(calls) == 1  # Save never generates a response.
    assert durations == ([1, 3, 2] if tail_seconds else [1, 1])
    with SessionLocal() as db:
        payload = checkin_payload(db.get(CheckIn, stream.checkin_id))
        history = payload['conversation_messages']
        assert [m['role'] for m in history] == ['assistant', 'user', 'assistant'] + (['user'] if tail_seconds else [])
        assert history[1]['text'] == 'Speech 1 (1.0s)'
        assert history[2]['text'] == 'Coach reply'
        if tail_seconds:
            assert history[-1]['text'] == 'Speech 3 (2.0s)' and history[-1]['status'] == 'saved'
        assert payload['transcript'] != history[1]['text']
        assert payload['completed_at']


@pytest.mark.asyncio
async def test_save_without_end_turn_reuses_full_transcript(turn_stream, monkeypatch):
    from app.services.transcribe import transcriber
    from app.api.checkins import checkin_payload
    stream, _ = turn_stream
    calls = []
    async def transcribe(audio):
        calls.append(audio)
        return 'Final speech'
    monkeypatch.setattr(transcriber(), 'transcribe', transcribe)
    await stream.start()
    await stream.ingest(b'\0\0' * 16000)
    await stream.finalize()
    assert len(calls) == 1
    with SessionLocal() as db:
        history = checkin_payload(db.get(CheckIn, stream.checkin_id))['conversation_messages']
        assert [m['text'] for m in history] == ['How are you feeling today?', 'Final speech']
        assert history[-1]['status'] == 'saved'


@pytest.mark.asyncio
@pytest.mark.parametrize('resume_after_failure', [False, True])
async def test_save_after_failed_end_turn_has_no_duplicate_speech(turn_stream, monkeypatch, resume_after_failure):
    from app.api.checkins import checkin_payload
    stream, _ = turn_stream
    async def reply(self, messages, *, history_context=None):
        raise ConversationError('Provider unavailable')
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    await stream.start()
    await stream.ingest(b'\0\0' * 16000)
    await stream.end_turn()
    await stream.turn_task
    if resume_after_failure:
        await stream.resume()
        await stream.ingest(b'\0\0' * 16000)
    await stream.finalize()
    with SessionLocal() as db:
        turns = list(db.scalars(select(ConversationTurn).where(ConversationTurn.checkin_id == stream.checkin_id)))
        assert len(turns) == (2 if resume_after_failure else 1)
        history = checkin_payload(db.get(CheckIn, stream.checkin_id))['conversation_messages']
        assert len(history) == 2 and history[-1]['status'] == 'saved'


@pytest.mark.asyncio
async def test_failed_final_transcription_keeps_prior_exchange_and_completes(turn_stream, monkeypatch):
    from app.api.checkins import checkin_payload
    from app.services.transcribe import transcriber
    stream, _ = turn_stream
    async def reply(self, messages, *, history_context=None):
        return {'reply': 'Earlier reply', 'model': 'test', 'raw_response': {}}
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    await stream.start()
    await stream.ingest(b'\0\0' * 16000)
    await stream.end_turn()
    await stream.turn_task
    await stream.resume()
    await stream.ingest(b'\0\0' * 16000)
    async def fail(audio):
        raise RuntimeError('Whisper unavailable')
    monkeypatch.setattr(transcriber(), 'transcribe', fail)
    await stream.finalize()
    with SessionLocal() as db:
        payload = checkin_payload(db.get(CheckIn, stream.checkin_id))
        assert payload['completed_at']
        assert payload['conversation_messages'][2]['text'] == 'Earlier reply'
        assert payload['conversation_messages'][-1]['status'] == 'transcription_failed'
        assert payload['conversation_messages'][-1]['error']
