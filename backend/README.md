# Vocal Biomarkers backend

The FastAPI service accepts 16 kHz mono signed-16-bit PCM through an authenticated,
one-use WebSocket session. It writes the complete normalized WAV, Pulse jobs, the final
Pulse JSON payload, and a transcript of the recording to Postgres.

## Run locally

1. Copy `.env.example` to `.env` and replace `APP_API_TOKEN`. Add the Amplifier
   account values when they are available; without them, Pulse uses a safe local mock.
2. From this directory, run `docker compose up --build`.
3. The API is then available at `http://127.0.0.1:8000`. Set the React app's
   `VITE_VOCAL_API_URL` and `VITE_VOCAL_API_TOKEN` to point to it.

This prototype intentionally has only these tables: `users`, `checkins`, `recordings`,
`amplifier_jobs`, `checkin_signals`, `interventions`, and `user_interventions`. The latter
records which interventions the private MVP user is currently doing. `checkin_signals`
holds one row per Amplifier signal per check-in, including the longitudinal fields
(`baseline_score`, `deviation_from_baseline`, `anomaly`, `z_score`, `population_z`). Those
are `null` until the subject's group has an established baseline — Amplifier's own
minimum is three spaced readings, and readings taken close together count as roughly one.
Gate any trend or intervention-effect analysis on `baseline_score is not None`, not on a
locally tracked reading count.

`checkins.transcript` holds a local speech-to-text transcription of the check-in's full
recording (faster-whisper, `WHISPER_MODEL` default `base`) — one pass over the whole
clip at `checkin.end`, not per-chunk, since a check-in is one person's own short
recording, not a two-party encounter needing live partial text. No audio leaves the
server for this step. `transcribed_at` is set once transcription has been attempted,
success or failure, and gates completion the same way an AmplifierJob's terminal status
does — `transcript` staying `null` alone can't distinguish "not attempted yet" from
"attempted, got nothing." Whisper's model weights download on first real (non-mock) use
and are cached in the container, so expect the first transcription after a fresh build
to be slower than later ones.

If you ran an older version of this prototype with Docker, reset its development-only
database volume before starting this schema:

```bash
docker compose down -v
docker compose up --build
```

This deletes local Postgres data. Do not use it against a database containing recordings
or data you need to keep.

For a non-Docker local run, create a virtual environment, install `requirements.txt`,
and use `uvicorn app.main:app --reload` from `backend/`.

## Privacy boundary

The browser only receives an app bearer token and a short-lived, one-use stream ticket.
Amplifier account credentials and webhook secrets stay on the server. Raw WAV recordings
and the Pulse response are retained in Postgres for this MVP and recordings can be replayed
through the authenticated recording endpoint.

## Protocol

Create a check-in with `POST /v1/checkins` using `Authorization: Bearer <token>`, then
connect to the returned `stream_path`. Send a JSON `checkin.start` control frame declaring
`pcm_s16le` at 16000 Hz, followed by binary PCM frames. Use `checkin.pause`,
`checkin.resume`, and `checkin.end` for the existing recorder controls. The service emits
`recording`, `processing`, `analyzing` (per Amplifier chunk, carries `chunk`),
`transcribing`, `transcript`, `result`, and `error` events — enough for a client to
narrate what's happening in real time rather than showing a bare spinner.

After `checkin.end`, the connection stays open until every queued Amplifier chunk and the
recording's transcription both complete, then emits `result` (or `error` per failed
chunk/transcription) before closing — it does not close as soon as `checkin.end` is
handled. If that takes longer than `FINALIZE_TIMEOUT_SECONDS` (default 120s), the
connection instead emits an `error` with `code: "processing_timeout"` and closes; the
check-in's own jobs keep running and will still complete in the background (poll
`GET /v1/checkins/{id}` or wait for the webhook), since `apply_job_result` is idempotent
regardless of which path reports first.

Pulse receives non-overlapping 30-second WAV segments through its signed-upload flow with
`diarize=false`, submitted to the group-aware longitudinal endpoint
(`POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`) rather than a one-off
score. `group_id` is derived per-user (`user-<user_id>`, see `pulse_group_id` in
`app/amplifier.py`) — a longitudinal group represents exactly one subject, so groups are
never shared across members. Each chunk's `recorded_at` is the check-in's own start time
plus that chunk's offset, so history stays correctly ordered even under retry.
`POST /v1/webhooks/amplifier` verifies the HMAC signature, and the per-job updates
(including writing `checkin_signals` rows) are idempotent — a job already marked
complete is a no-op, whichever path reports it first.
