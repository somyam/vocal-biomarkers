# Vocal Biomarkers backend

The FastAPI service accepts 16 kHz mono signed-16-bit PCM through an authenticated,
one-use WebSocket session. It writes the complete normalized WAV, the non-overlapping
30-second analysis windows, Pulse jobs, and user-facing summaries to Postgres.

## Run locally

1. Copy `.env.example` to `.env` and replace `APP_API_TOKEN`. Add the Amplifier
   account values when they are available; without them, Pulse uses a safe local mock.
2. From this directory, run `docker compose up --build`.
3. The API is then available at `http://127.0.0.1:8000`. Set the React app's
   `VITE_VOCAL_API_URL` and `VITE_VOCAL_API_TOKEN` to point to it.

For a non-Docker local run, create a virtual environment, install `requirements.txt`,
and use `uvicorn app.main:app --reload` from `backend/`.

## Privacy boundary

The browser only receives an app bearer token and a short-lived, one-use stream ticket.
Amplifier account credentials and webhook secrets stay on the server. Raw WAV recordings
are intentionally retained in Postgres for the MVP and can be replayed through the
authenticated recording endpoint. Pulse responses are stored for auditability but the API
returns only recording-quality messages and non-diagnostic trend summaries to the UI.

## Protocol

Create a check-in with `POST /v1/checkins` using `Authorization: Bearer <token>`, then
connect to the returned `stream_path`. Send a JSON `checkin.start` control frame declaring
`pcm_s16le` at 16000 Hz, followed by binary PCM frames. Use `checkin.pause`,
`checkin.resume`, and `checkin.end` for the existing recorder controls. The service emits
`recording`, `queued`, `processing`, `quality`, `result`, and `error` events.

Pulse receives non-overlapping 30-second WAV segments through its signed-upload flow with
`diarize=false`. `POST /v1/webhooks/amplifier` verifies the HMAC signature, and the
per-job updates are idempotent.
