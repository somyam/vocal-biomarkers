# Vocal Biomarkers

A mobile app prototype for a longevity/wellness membership: a daily habit tracker
paired with a voice "Morning Check-in" that's scored for wellness signals — mood
disruption, anxiety, stress, fatigue, elevated blood pressure, and dehydration —
via Amplifier's Pulse API. 

https://github.com/user-attachments/assets/17e03165-f222-4d02-bc8e-31601f13e025

## In this repo

The application has two parts: a browser frontend and a Python backend. The
backend connects to Postgres, AMPLIFIER, and Anthropic Claude.

| Location | Responsibility |
| --- | --- |
| [`apps/web/`](apps/web/) | React + TypeScript frontend: habit tracking, microphone capture, live captions, conversation history, and text chat. It runs inside an iPhone/Android simulator with shared scrolling and keyboard controls. |
| [`apps/api/`](apps/api/) | FastAPI backend: receives audio, transcribes it locally with faster-whisper, requests AMPLIFIER analysis and Claude replies, and persists recordings, signals, and conversations in Postgres. Docker Compose runs one API process and Postgres, with an optional ngrok webhook tunnel. |
| [`apps/web/public/presentation.html`](apps/web/public/presentation.html) | Presentation view within the frontend: embeds the scripted app beside an event log. It is a demo, not a separate backend service. |

**In live mode**, the browser streams 16 kHz mono audio to the backend over a
WebSocket. The backend updates captions and sends AMPLIFIER up to 30 seconds of
audio every 15 seconds: `0–15`, `0–30`, `15–45`, and so on. **End Turn** pauses
capture and requests a Claude reply using the transcript, previous turns, and
prompt caching. **Save Conversation** saves the full recording and shows the
complete conversation, which can continue through text messages over HTTP as soon
as recording/transcription finish—even while analysis is pending. AMPLIFIER sends
signed webhooks to the backend. A separate authenticated notification WebSocket
pushes saved conversation and analysis snapshots to the browser. There is no
automatic status polling; **Check analysis once** is an explicit recovery action.

**Demo versus live:** `/?member=1` uses scripted responses and does not require
the backend. `/?member=1&live=1` enables real microphone capture and backend
requests. External analysis and replies require the corresponding server-side
API credentials; real AMPLIFIER submissions also require a public HTTPS webhook URL
and signing secret (see [local webhook setup](apps/api/README.md#local-webhook-setup)). AMPLIFIER falls back to mock results when its keys are absent.

For UI changes, start with `apps/web/src/Prototype.tsx` and
`apps/web/src/prototype.css`; see [AGENTS.md](AGENTS.md) for protected mobile-runtime
files. For endpoints, audio processing, configuration, and database tables, see
the [backend README](apps/api/README.md).

## Running the application

**Frontend (scripted demo):**

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173/` for the two-panel demo view (phone + live trace
panel), `http://localhost:5173/?member=1` for just the bare app, or
`http://localhost:5173/?member=1&live=1` for the bare app wired to a real
backend (requires the backend running — see below).

**Backend (real check-in pipeline):**

```bash
cd apps/api
cp .env.example .env   # set APP_API_TOKEN; Amplifier keys optional — falls back to a safe mock
docker compose up --build
```

For real AMPLIFIER analysis, configure the static ngrok domain and token in the
ignored backend `.env`, then use `docker compose --profile webhooks up --build`.
The public tunnel accepts only the signed webhook route.

Then point the frontend at it via `apps/web/.env` (see `apps/web/.env.example`):

```
VITE_VOCAL_API_URL=http://127.0.0.1:8000
VITE_VOCAL_API_TOKEN=development-token
```

Then open `http://localhost:5173/?member=1&live=1` (see above) — the `live`
flag is what switches Morning Check-in to this real mic + WebSocket + backend
flow. Without it, the frontend always shows the scripted demo, even with the
backend running.

## Other scripts

Run from `apps/web/`:

- `npm run check:runtime` — verifies the protected mobile-device runtime files haven't drifted.
- `npm run build` — typechecks and builds the app.
- `npm run test:runtime` — Playwright tests for the device runtime.
