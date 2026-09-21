from fastapi.testclient import TestClient

from app.main import app


HEADERS = {"Authorization": "Bearer development-token"}


def test_checkin_creation_requires_bearer_token():
    with TestClient(app) as client:
        assert client.post("/v1/checkins", json={}).status_code == 401
        response = client.post("/v1/checkins", json={}, headers=HEADERS)
        assert response.status_code == 201
        payload = response.json()
        assert payload["checkin"]["status"] == "created"
        assert payload["stream_ticket"]


def test_stream_ticket_is_accepted_once_and_pcm_windows_are_persisted():
    with TestClient(app) as client:
        created = client.post("/v1/checkins", json={}, headers=HEADERS).json()
        checkin_id = created["checkin"]["id"]
        path = created["stream_path"]
        with client.websocket_connect(path) as socket:
            assert socket.receive_json()["type"] == "connected"
            socket.send_json({"type": "checkin.start", "sample_rate": 16000, "encoding": "pcm_s16le"})
            socket.receive_json()
            socket.send_bytes(b"\0\0" * (16_000 * 60))
            socket.send_json({"type": "checkin.end"})
        saved = client.post(f"/v1/checkins/{checkin_id}/finish", headers=HEADERS)
        assert saved.status_code == 200
        assert saved.json()["duration_seconds"] == 60
        recording = client.get(f"/v1/checkins/{checkin_id}/recording", headers=HEADERS)
        assert recording.status_code == 200
        assert recording.content[:4] == b"RIFF"
