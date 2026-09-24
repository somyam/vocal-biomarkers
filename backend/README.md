## Run Agent

1. Copy `.env.example` to `.env`.
2. From this directory, run `docker compose up --build` (or, without Docker,
   create a Python venv, install `requirements.txt`, and run
   `uvicorn app.main:app --reload`).
3. The API is then available at `http://127.0.0.1:8000`. Set the React app's
   `VITE_VOCAL_API_URL` and `VITE_VOCAL_API_TOKEN` to point to it.

## Protocol

Pulse receives 30-second sliding window WAV segments with a 15 second stride, submitted to the group-aware longitudinal endpoint
(`POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`) rather than a one-off
score. `group_id` is derived per-user (`user-<user_id>`, see `pulse_group_id` in
`app/amplifier.py`) — a longitudinal group represents exactly one subject, so groups are
never shared across members.

The FastAPI service accepts 16 kHz mono signed-16-bit PCM through an authenticated,
one-use WebSocket session. It writes the complete normalized WAV, Pulse jobs, the final
Pulse JSON payload, and a transcript of the recording to Postgres.

## Data model
The backend has these postgres tables: `users`, `checkins`, `recordings`,
`amplifier_jobs`, `checkin_signals`, `interventions`, and `user_interventions`. The latter
records which interventions the private MVP user is currently doing. `checkin_signals`
holds one row per Amplifier signal per check-in, including the longitudinal fields
(`baseline_score`, `deviation_from_baseline`, `anomaly`, `z_score`, `population_z`). Those
are `null` until the subject's group has an established baseline.
Gate any trend or intervention-effect analysis on `baseline_score is not None`.

`checkins.transcript` holds a local speech-to-text transcription of the check-in's full
recording (faster-whisper, `WHISPER_MODEL` default `base`) — one pass over the whole
clip at `checkin.end`.

