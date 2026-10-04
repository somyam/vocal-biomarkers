import asyncio
import uuid
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import SessionLocal
from app.models import CheckIn, ConversationTurn, ConversationTextTurn, User
from app.services.conversation import ConversationError, SonnetClient

HEADERS = {'Authorization': 'Bearer development-token'}


@pytest.fixture
def saved_checkin():
    with TestClient(app) as client:
        checkin_id = client.post('/v1/checkins', headers=HEADERS).json()['checkin']['checkin_id']
    with SessionLocal() as db:
        db.get(CheckIn, checkin_id).recording_completed_at = datetime.now()
        db.get(CheckIn, checkin_id).completed_at = datetime.now()
        db.add_all([
            ConversationTurn(checkin_id=checkin_id, start_sample=0, end_sample=16000,
                             status='done', transcript='Spoken first turn', reply='Voice reply'),
            ConversationTurn(checkin_id=checkin_id, start_sample=16000, end_sample=32000,
                             status='saved', transcript='Final saved speech'),
        ])
        db.commit()
    return checkin_id


def test_text_continuation_history_idempotency_and_persistence(saved_checkin, monkeypatch):
    calls = []
    async def reply(self, messages):
        calls.append(messages)
        return {'reply': f'Text reply {len(calls)}', 'model': 'test',
                'raw_response': {'id': f'msg-{len(calls)}', 'usage': {'cache_read_input_tokens': 600}}}
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    path = f'/v1/checkins/{saved_checkin}/messages'
    first = {'request_id': str(uuid.uuid4()), 'text': '  First typed message  '}
    with TestClient(app) as client:
        result = client.post(path, headers=HEADERS, json=first)
        assert result.status_code == 200
        assert client.post(path, headers=HEADERS, json=first).json() == result.json()
        assert client.post(path, headers=HEADERS, json={**first, 'text': 'Different'}).status_code == 409
        assert client.post(path, headers=HEADERS, json={'request_id': str(uuid.uuid4()), 'text': 'Next message'}).status_code == 200
        history = client.get(f'/v1/checkins/{saved_checkin}', headers=HEADERS).json()['conversation_messages']
        assert [m['text'] for m in history] == ['How are you feeling today?', 'Spoken first turn', 'Voice reply',
            'Final saved speech', 'First typed message', 'Text reply 1', 'Next message', 'Text reply 2']
    assert calls[0] == [{'role': 'user', 'content': 'Spoken first turn'}, {'role': 'assistant', 'content': 'Voice reply'},
                        {'role': 'user', 'content': 'Final saved speech'}, {'role': 'user', 'content': 'First typed message'}]
    assert calls[1][:-1] == [*calls[0], {'role': 'assistant', 'content': 'Text reply 1'}]
    with SessionLocal() as db:
        rows = list(db.scalars(select(ConversationTextTurn).where(ConversationTextTurn.checkin_id == saved_checkin)))
        assert len(rows) == 2
        assert all(t.completed_at and t.status == 'done' and t.raw_response['usage']['cache_read_input_tokens'] == 600 for t in rows)


def test_failed_text_retry_uses_same_row_and_preserves_message(saved_checkin, monkeypatch):
    calls = []
    async def reply(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            raise ConversationError('Temporary failure')
        return {'reply': 'Recovered', 'model': 'test', 'raw_response': {}}
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    body = {'request_id': str(uuid.uuid4()), 'text': 'Keep this message'}
    path = f'/v1/checkins/{saved_checkin}/messages'
    with TestClient(app) as client:
        first = client.post(path, headers=HEADERS, json=body).json()
        assert first['conversation_messages'][-1]['status'] == 'failed'
        assert client.post(path, headers=HEADERS, json={**body, 'request_id': str(uuid.uuid4())}).status_code == 409
        second = client.post(path, headers=HEADERS, json=body).json()
        assert second['conversation_messages'][-1]['text'] == 'Recovered'
    assert calls[0] == calls[1]
    with SessionLocal() as db:
        rows = list(db.scalars(select(ConversationTextTurn).where(ConversationTextTurn.checkin_id == saved_checkin)))
        assert len(rows) == 1 and rows[0].error is None


def test_message_auth_completion_and_validation(saved_checkin):
    body = {'request_id': str(uuid.uuid4()), 'text': 'Hello'}
    with TestClient(app) as client:
        path = f'/v1/checkins/{saved_checkin}/messages'
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, headers=HEADERS, json={**body, 'text': '   '}).status_code == 422
        assert client.post(path, headers=HEADERS, json={**body, 'text': 'a' * 10001}).status_code == 422
        unsaved = client.post('/v1/checkins', headers=HEADERS).json()['checkin']['checkin_id']
        assert client.post(f'/v1/checkins/{unsaved}/messages', headers=HEADERS, json=body).status_code == 409
        with SessionLocal() as db:
            user = User(user_id=str(uuid.uuid4()))
            db.add(user)
            db.flush()
            db.get(CheckIn, saved_checkin).user_id = user.user_id
            db.commit()
        assert client.post(path, headers=HEADERS, json=body).status_code == 404
        assert client.get(f'/v1/checkins/{saved_checkin}', headers=HEADERS).status_code == 404


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_only_call_claude_once(saved_checkin, monkeypatch):
    gate, entered = asyncio.Event(), asyncio.Event()
    calls = []
    async def reply(self, messages):
        calls.append(messages)
        entered.set()
        await gate.wait()
        return {'reply': 'Only once', 'model': 'test', 'raw_response': {}}
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        path = f'/v1/checkins/{saved_checkin}/messages'
        body = {'request_id': str(uuid.uuid4()), 'text': 'Hello'}
        first = asyncio.create_task(client.post(path, headers=HEADERS, json=body))
        await entered.wait()
        second = asyncio.create_task(client.post(path, headers=HEADERS, json=body))
        await asyncio.sleep(0)
        gate.set()
        results = await asyncio.gather(first, second)
        assert all(response.status_code == 200 for response in results)
        assert len(calls) == 1


def test_restart_makes_interrupted_text_retryable_without_provider_call(saved_checkin, monkeypatch):
    calls = []
    async def reply(self, messages):
        calls.append(messages)
        return {'reply': 'Recovered after restart', 'model': 'test', 'raw_response': {}}
    monkeypatch.setattr(SonnetClient, 'reply', reply)
    request_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(ConversationTextTurn(request_id=request_id, checkin_id=saved_checkin, text='Keep this', status='processing'))
        db.commit()
    with TestClient(app) as client:
        message = client.get(f'/v1/checkins/{saved_checkin}', headers=HEADERS).json()['conversation_messages'][-1]
        assert message['text'] == 'Keep this' and message['status'] == 'failed'
        assert 'restarted' in message['error']
        assert calls == []
        response = client.post(f'/v1/checkins/{saved_checkin}/messages', headers=HEADERS,
                               json={'request_id': request_id, 'text': 'Keep this'})
        assert response.status_code == 200
        assert response.json()['conversation_messages'][-1]['status'] == 'done'
