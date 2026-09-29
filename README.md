# Vocal Biomarkers

A mobile app prototype for a longevity/wellness membership: a daily habit tracker
paired with a voice "Morning Check-in" that's scored for wellness signals — mood
disruption, anxiety, stress, fatigue, elevated blood pressure, and dehydration —
via Amplifier's Pulse API. 

https://github.com/user-attachments/assets/17e03165-f222-4d02-bc8e-31601f13e025

## In this repo

Two deployables live under `apps/`:

**`apps/web/` — the mobile app.** React + TypeScript, rendered inside a calibrated device-simulator runtime (apps/web/src/mobile/: iPhone and Pixel 10 frames, live status bar, on-screen keyboard). All app-specific screens and logic live in apps/web/src/Prototype.tsx and apps/web/src/prototype.css — everything else under apps/web/src/ is protected scaffold (see AGENTS.md).

**`apps/api/` — FastAPI + Postgres, dockerized.** Streams live
16kHz PCM audio over WebSocket, transcribes it locally (faster-whisper), and
submits 30-second chunks with a 15 second hop to Amplifier's longitudinal
Pulse endpoint (`POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`)
so each reading is scored against that subject's own history. Results land in
Postgres.

**`apps/web/public/presentation.html` — the mock demo.** A two-panel view (phone
mockup + "Live Agent Trace" log) that the app pushes `postMessage` events into,
narrating what the API calls, signal levels, and agent reasoning would look
like during an example check-in.

The real, working backend pipeline is the backend described in apps/api/README.md. It includes WebSocket streaming, live transcription, real Amplifier API requests. The apps/api/ folder is not wired up to this particular scripted demo screen for presentation purposes.

## Running the application

**Frontend (scripted demo):**

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173/` for the two-panel demo view (phone + live trace
panel), or `http://localhost:5173/?member=1` for just the bare app.

**Backend (real check-in pipeline):**

```bash
cd apps/api
cp .env.example .env   # set APP_API_TOKEN; Amplifier keys optional — falls back to a safe mock
docker compose up --build
```

Then point the frontend at it via `apps/web/.env` (see `apps/web/.env.example`):

```
VITE_VOCAL_API_URL=http://127.0.0.1:8000
VITE_VOCAL_API_TOKEN=development-token
```

## Other scripts

Run from `apps/web/`:

- `npm run check:runtime` — verifies the protected mobile-device runtime files haven't drifted.
- `npm run build` — typechecks and builds the app.
- `npm run test:runtime` — Playwright tests for the device runtime.
