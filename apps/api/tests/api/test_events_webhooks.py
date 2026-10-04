import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AmplifierJob, CheckIn, CheckInSignal, User, WebhookInbox
from app.api.events import event_tickets
from app.services import analysis
from app.services.amplifier import PulseClient

HEADERS = {'Authorization': 'Bearer development-token'}


def payload(job):
    return {'job_id': job, 'status': 'done', 'result': {'signals': [
        {'name': 'stress', 'score': 0.7, 'level': 'high', 'flagged': True, 'baseline_score': None}],
        'extended_metrics': {'kept': [1, 2, 3]}}}


def deliver(client, body, valid=True):
    raw = json.dumps(body).encode()
    signature = hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest() if valid else 'invalid'
    return client.post('/v1/webhooks/amplifier', content=raw, headers={'X-Webhook-Signature': signature})


def setup_checkin(client, monkeypatch):
    monkeypatch.setattr(settings(), 'amplifier_webhook_secret', 'test-secret')
    created = client.post('/v1/checkins', headers=HEADERS).json()
    checkin_id = created['checkin']['checkin_id']
    with SessionLocal() as db:
        db.get(CheckIn, checkin_id).recording_completed_at = datetime.now()
        db.commit()
    return checkin_id, created


def register(checkin_id, job=None):
    job = job or str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(AmplifierJob(job_id=job, checkin_id=checkin_id))
        db.commit()
    return job


def ticket(client, checkin_id):
    response = client.post(f'/v1/checkins/{checkin_id}/events-ticket', headers=HEADERS)
    assert response.status_code == 200
    return response.json()['events_path']


def test_signed_early_duplicate_invalid_and_full_persistence(monkeypatch):
    with TestClient(app) as client:
        checkin, _ = setup_checkin(client, monkeypatch)
        job = str(uuid.uuid4())
        body = payload(job)
        assert deliver(client, body, valid=False).status_code == 401
        assert deliver(client, {'job_id': job, 'status': 'done', 'result': {'signals': [{'name': 'bad', 'score': 'NaN'}]}}).status_code == 400
        assert deliver(client, body).json() == {'accepted': True, 'applied': False}
        with SessionLocal() as db:
            assert db.get(WebhookInbox, job).applied_at is None
        register(checkin, job)
        assert client.portal.call(analysis.reconcile_inbox, job)
        assert deliver(client, body).json() == {'accepted': True, 'applied': False}
        with SessionLocal() as db:
            assert db.get(WebhookInbox, job).applied_at
            assert db.get(AmplifierJob, job).raw_response == body
            signals = list(db.scalars(select(CheckInSignal).where(CheckInSignal.checkin_id == checkin)))
            assert len(signals) == 1 and signals[0].score == 0.7 and signals[0].baseline_score is None
            assert db.get(CheckIn, checkin).completed_at


def test_notifications_multiple_subscribers_text_while_pending_and_reconnect(monkeypatch):
    async def no_get(*args):
        pytest.fail('Normal operation must not request job status')
    monkeypatch.setattr(PulseClient, 'get_result_once', no_get)
    with TestClient(app) as client:
        checkin, _ = setup_checkin(client, monkeypatch)
        job = register(checkin)
        first_path = ticket(client, checkin)
        with client.websocket_connect(first_path) as first, client.websocket_connect(ticket(client, checkin)) as second:
            for socket in (first, second):
                snapshot = socket.receive_json()['checkin']
                assert snapshot['recording_completed_at'] and not snapshot['completed_at']
                assert snapshot['analysis_status'] == 'pending'
            reply = client.post(f'/v1/checkins/{checkin}/messages', headers=HEADERS,
                                json={'request_id': str(uuid.uuid4()), 'text': 'Can chat while pending'})
            assert reply.status_code == 200
            assert deliver(client, payload(job)).json()['applied']
            for socket in (first, second):
                for _ in range(6):
                    event = socket.receive_json()
                    if event['checkin']['analysis_status'] == 'complete':
                        break
                assert event['sequence'] > 0
                assert event['checkin']['completed_at']
                assert any(m['text'] == 'Can chat while pending' for m in event['checkin']['conversation_messages'])
        with client.websocket_connect(ticket(client, checkin)) as reopened:
            assert reopened.receive_json()['checkin']['analysis_status'] == 'complete'
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(first_path):
                pass


def test_event_tickets_ownership_expiry_and_audio_separation(monkeypatch):
    with TestClient(app) as client:
        checkin, created = setup_checkin(client, monkeypatch)
        assert client.post(f'/v1/checkins/{checkin}/events-ticket').status_code == 401
        with SessionLocal() as db:
            user = User(user_id=str(uuid.uuid4()))
            db.add(user)
            db.flush()
            other = CheckIn(user_id=user.user_id)
            db.add(other)
            db.commit()
            other_id = other.checkin_id
        for suffix in ('events-ticket', 'analysis/refresh'):
            assert client.post(f'/v1/checkins/{other_id}/{suffix}', headers=HEADERS).status_code == 404
        paths = [f'/v1/checkins/{checkin}/events?ticket={created["stream_ticket"]}', ticket(client, checkin)]
        token = paths[-1].split('ticket=')[1]
        event_tickets._tickets[token].expires_at = 0
        for path in paths:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(path):
                    pass


def test_delayed_notification_late_webhook_and_explicit_recovery(monkeypatch):
    calls = []
    async def get_once(self, job):
        calls.append(job)
        return payload(job)
    monkeypatch.setattr(PulseClient, 'get_result_once', get_once)
    monkeypatch.setattr(settings(), 'analysis_delay_seconds', 0.04)
    with TestClient(app) as client:
        checkin, _ = setup_checkin(client, monkeypatch)
        job = register(checkin)
        with client.websocket_connect(ticket(client, checkin)) as socket:
            assert socket.receive_json()['checkin']['analysis_status'] == 'pending'
            with SessionLocal() as db:
                created = db.get(AmplifierJob, job).created_at
            async def schedule():
                analysis.schedule_deadline('job:' + job, checkin, created)
            client.portal.call(schedule)
            assert socket.receive_json()['checkin']['analysis_status'] == 'delayed'
            assert calls == []
            assert deliver(client, payload(job)).status_code == 200
            assert socket.receive_json()['checkin']['analysis_status'] == 'complete'
        second = register(checkin)
        response = client.post(f'/v1/checkins/{checkin}/analysis/refresh', headers=HEADERS)
        assert response.json()['analysis_status'] == 'complete'
        assert calls == [second]
        client.post(f'/v1/checkins/{checkin}/analysis/refresh', headers=HEADERS)
        assert calls == [second]


def test_subscribe_precedes_snapshot_and_update_during_snapshot_is_not_lost(monkeypatch):
    from app.api import events
    original = events.checkin_payload
    with TestClient(app) as client:
        checkin, _ = setup_checkin(client, monkeypatch)
        changed = False
        def snapshot(row):
            nonlocal changed
            value = original(row)
            if row.checkin_id == checkin and not changed:
                changed = True
                with SessionLocal() as db:
                    db.get(CheckIn, checkin).transcript = 'Changed during snapshot'
                    db.commit()
                events.notifications.publish(checkin)
            return value
        monkeypatch.setattr(events, 'checkin_payload', snapshot)
        with client.websocket_connect(ticket(client, checkin)) as socket:
            assert socket.receive_json()['checkin']['transcript'] is None
            assert socket.receive_json()['checkin']['transcript'] == 'Changed during snapshot'
