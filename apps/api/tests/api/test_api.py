from fastapi.testclient import TestClient

from app.main import app


HEADERS = {"Authorization": "Bearer development-token"}


def test_checkin_creation_requires_bearer_token():
    with TestClient(app) as client:
        assert client.post("/v1/checkins", json={}).status_code == 401
        response = client.post("/v1/checkins", json={}, headers=HEADERS)
        assert response.status_code == 201
        payload = response.json()
        assert payload["checkin"]["checkin_id"]
        assert payload["stream_ticket"]


def test_seeded_user_interventions_can_be_read_and_stopped():
    with TestClient(app) as client:
        items = client.get("/v1/user-interventions", headers=HEADERS).json()["items"]
        assert items
        assert "guide_text" in items[0]
        stopped = client.patch(f"/v1/user-interventions/{items[0]['user_intervention_id']}",
            headers=HEADERS, json={"active": False})
        assert stopped.status_code == 200
        assert stopped.json()["active"] is False


def test_stream_ticket_is_accepted_once_and_pcm_windows_are_persisted():
    with TestClient(app) as client:
        created = client.post("/v1/checkins", json={}, headers=HEADERS).json()
        checkin_id = created["checkin"]["checkin_id"]
        path = created["stream_path"]
        with client.websocket_connect(path) as socket:
            assert socket.receive_json()["type"] == "connected"
            socket.send_json({"type": "checkin.start", "sample_rate": 16000, "encoding": "pcm_s16le"})
            socket.receive_json()
            socket.send_bytes(b"\0\0" * (16_000 * 46))
            socket.send_json({"type": "checkin.end"})
            windows = []
            while True:
                event = socket.receive_json()
                if event["type"] == "analyzing":
                    windows.append((event["start_seconds"], event["end_seconds"]))
                if event["type"] == "result":
                    break
            assert windows == [(0, 15), (0, 30), (15, 45)]
        saved = client.post(f"/v1/checkins/{checkin_id}/finish", headers=HEADERS)
        assert saved.status_code == 200
        assert saved.json()["duration_seconds"] == 46
        assert saved.json()["completed_at"] is not None
        assert len(saved.json()["pulse_json"]["jobs"]) == 3
        recording = client.get(f"/v1/checkins/{checkin_id}/recording", headers=HEADERS)
        assert recording.status_code == 200
        assert recording.content[:4] == b"RIFF"


def test_end_turn_websocket_saves_conversation_and_cache_usage(monkeypatch):
    import json
    import httpx
    from app.core.config import settings

    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": f"msg-{len(requests)}", "model": "test-sonnet",
            "content": [{"type": "text", "text": f"Reply {len(requests)}"}],
            "usage": {"cache_creation_input_tokens": 512, "cache_read_input_tokens": 512 if len(requests) > 1 else 0}})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(settings(), "anthropic_api_key", "test-server-key")
    with TestClient(app) as client:
        created = client.post("/v1/checkins", json={}, headers=HEADERS).json()
        checkin_id = created["checkin"]["checkin_id"]
        with client.websocket_connect(created["stream_path"]) as socket:
            assert socket.receive_json()["type"] == "connected"
            socket.send_json({"type": "checkin.start"})
            for index in range(2):
                socket.send_bytes(b"\0\0" * 16000)
                socket.send_json({"type": "checkin.turn.end"})
                while True:
                    event = socket.receive_json()
                    assert event["type"] != "error", event
                    if event["type"] == "turn_result":
                        assert event["reply"] == f"Reply {index + 1}"
                        break
                if index == 0:
                    socket.send_json({"type": "checkin.resume"})
            socket.send_json({"type": "checkin.end"})
            while socket.receive_json()["type"] != "result":
                pass
        saved = client.get(f"/v1/checkins/{checkin_id}", headers=HEADERS).json()
        assert saved["completed_at"] and saved["duration_seconds"] == 2
        assert len(saved["conversation_turns"]) == 2
        assert saved["conversation_turns"][1]["usage"]["cache_read_input_tokens"] == 512
        assert len(requests) == 2  # Save never invokes Claude.
        assert all(body["cache_control"] == {"type": "ephemeral", "ttl": "5m"} for body in requests)
        assert requests[1]["system"] == requests[0]["system"]
        assert requests[1]["messages"] == [*requests[0]["messages"],
            {"role": "assistant", "content": "Reply 1"}, {"role": "user", "content": "[mock transcript]"}]
