# Vocal Biomarkers

A mobile app prototype for a longevity/wellness membership: a daily habit tracker
paired with a voice "Morning Check-in" that's scored for wellness signals — mood
disruption, anxiety, stress, fatigue, elevated blood pressure, and dehydration —
via Amplifier's Pulse API. 

https://github.com/user-attachments/assets/17e03165-f222-4d02-bc8e-31601f13e025

## What's in this repo

**`src/` — the mobile app.** React + TypeScript, rendered inside a calibrated device-simulator runtime (src/mobile/: iPhone and Pixel 10 frames, live status bar, on-screen keyboard). All app-specific screens and logic live in src/Prototype.tsx and src/prototype.css — everything else under src/ is protected scaffold (see AGENTS.md).

**`backend/` ** FastAPI + Postgres, dockerized. Streams live
16kHz PCM audio over WebSocket, transcribes it locally (faster-whisper), and
submits 30-second chunks with a 15 second hop to Amplifier's longitudinal
Pulse endpoint (`POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`)
so each reading is scored against that subject's own history. Results land in
Postgres.

**`public/presentation.html` — the mock demo.** A two-panel view (phone
mockup + "Live Agent Trace" log) that the app pushes `postMessage` events into,
narrating what the API calls, signal levels, and agent reasoning would look
like during an example check-in.

The real, working backend pipeline is the backend described in backend/README.md. It includes WebSocket streaming, live transcription, real Amplifier API requests. The backend/ folder is not wired up to this particular scripted demo screen for presentation purposes.

## Running the application

**Frontend (scripted demo):**

```bash
npm install
npm run dev
```

Open `http://localhost:5173/` for the two-panel demo view (phone + live trace
panel), or `http://localhost:5173/?member=1` for just the bare app.

**Backend (real check-in pipeline):**

```bash
cd backend
cp .env.example .env   # set APP_API_TOKEN; Amplifier keys optional — falls back to a safe mock
docker compose up --build
```

Then point the frontend at it via a root `.env` (see `.env.example`):

```
VITE_VOCAL_API_URL=http://127.0.0.1:8000
VITE_VOCAL_API_TOKEN=development-token
```

## Other scripts

- `npm run check:runtime` — verifies the protected mobile-device runtime files haven't drifted.
- `npm run build` — typechecks, builds, and prepares the Cloudflare Worker output for deployment.
- `npm run test:runtime` — Playwright tests for the device runtime.
