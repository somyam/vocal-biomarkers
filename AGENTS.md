# Vocal Biomarkers — Agent Guide

## Repository Layout

- **`apps/web/`** — React + TypeScript mobile prototype. Everything below applies only here.
- **`apps/api/`** — FastAPI + Postgres backend (WebSocket audio streaming, local transcription, Amplifier Pulse scoring). No prototype-runtime rules apply; see `apps/api/README.md` for protocol and data model. Code is split into `app/api/` (routers), `app/services/` (business logic), `app/core/` (auth/config/database).

## apps/web/ — Commands

Setup (once): `cd apps/web && npm install`.

Run from `apps/web/`:

- `npm run dev` — starts Vite at `http://localhost:5173/`; `predev` auto-runs `check:runtime` first.
- `npm run build` — `prebuild` auto-runs `check:runtime`, then typechecks and builds.
- `npm run check:runtime` — hashes the protected files below against `mobile-runtime.lock.json` and fails on drift.
- `npm run test:runtime` — Playwright tests for the device runtime.

If `check:runtime` fails, restore the protected file — do not edit the check or the lock file to make it pass. After an explicit, user-approved runtime change, regenerate the lock with `node scripts/update-mobile-runtime-lock.mjs`.

## apps/web/ — Protected Files

Do not edit, replace, remove, or recreate these unless the user explicitly asks to change the mobile runtime itself:

`src/App.tsx`, `src/main.tsx`, `src/styles.css`, `src/mobile/`, `public/assets/iphone/`, `public/assets/android/`, `public/assets/status/`, `vite.config.ts`.

App-specific UI belongs in `src/Prototype.tsx` and `src/prototype.css` — everything else is shared runtime scaffold.

## apps/web/ — Preview Workflow

- In ChatGPT Work Mode: run `sites-preview start "$PWD/apps/web"`, open `http://terminal.local:4173/` in the cloud browser. Keep the preview open and tell the user to inspect it there — never present the local URL as a user-facing chat link.
- In Codex Desktop: run the dev server yourself from `apps/web/`, open the preview in the in-app browser, and give the user the clickable local URL.
- Never deploy/publish/share unless the user explicitly asks.
- Don't give server-start instructions when you can run the server yourself.

## apps/web/ — Constraints

Cross-file invariants that aren't visible from reading any single component:

- **Device chrome vs. app content**: `PhoneFrame`, `StatusBar`, `HomeIndicator`, the device picker, and the camera cutout are protected runtime chrome, not app content — visual-fidelity work targets what renders inside the phone screen, not the chrome around it.
- **Live status bar**: `StatusBar` renders a real-time clock and live platform indicators. Never hardcode a screenshot time (e.g. `9:41`) or otherwise freeze it, unless the user explicitly asks for a fixed/mock device time.
- **Reach for the existing primitive, don't rebuild it**: `MobileScroll` for scrollable content, `FlowStack`/`FlowScreen` (via `flow.push`/`pop`/`replace`) for multi-screen flows with owned headers/footers, `Carousel` for horizontal collections, `BottomSheet` for phone-scoped sheets, `KeyboardInput`/`KeyboardTextarea`/`MobileTextField` for any text entry. A hand-rolled equivalent (raw `overflow-x`, custom pointer handlers, native `input`/`textarea`, a new router) silently disconnects from the keyboard insets, safe areas, or drag-suppression the shared primitive already wires up.
- **Keyboard dismissal is an explicit call, not a side effect**: `FlowStack` and `BottomSheet` already call `keyboard.hide()` on push/pop/replace/open — any *new* modal, sheet, or navigation primitive must call it too. Also call it on blur of any custom (non-runtime) text-entry control, and before a transition whose destination shouldn't inherit focus.
- **`useKeyboardInsets()` over ad hoc timers**: position custom fixed composers/search bars/toast chrome from `useKeyboardInsets().bottomInset`, not a separate visibility flag or timer — the two must dismiss together. Never pin custom bottom chrome to plain `bottom: 0` or raw `keyboardHeight` alone.
- **`FlowScreen.footer` is an overlay, not layout space**: screens using it must add their own bottom content padding (`calc(var(--flow-footer-height) + var(--mobile-safe-area-height) + <gap>)`) so scrollable content can pass under it.
- **Z-index layering**: home indicator (topmost safe-area layer) > keyboard > ordinary app UI. Fixed phone chrome (status bar, camera cutout, preview chrome) never animates with pushed screens, even though screen content does.
- **Drag vs. tap**: don't fire buttons/inputs once a pointer has become a drag, and don't allow native image/file drag inside the phone frame — both suppressions live in `MobileScroll`/phone-level handlers; preserve them rather than special-casing new interactive elements.
- Record durable, user-approved prototype design decisions in this file so they survive across sessions.

## Live check-in analysis cadence

- User-approved behavior: submit microphone audio to AMPLIFIER every 15 seconds of captured audio, using the latest up to 30 seconds (0–15, 0–30, 15–45, 30–60, etc.). Paused time does not count.
- Save persists the complete recording without an extra analysis submission. A 46-second recording produces exactly three scheduled submissions; recordings shorter than 15 seconds produce none.
- Pause must release microphone tracks, block queued PCM and late transcript updates, and hold new AMPLIFIER upload/analyze requests and queued retries. Resume reacquires microphone access and continues the same check-in; Save permits finishing pending work without reopening the microphone.
- Live recorder actions: “Save Conversation” finishes and saves the session; “End Turn” sits to its right, stops microphone capture, transcribes only the new turn, and sends it with prior turns to Anthropic Claude Sonnet using automatic prompt caching. Postgres retains the full turn history for replay; there is no OpenAI response-ID chain. Show the reply in the same conversation and keep the microphone paused until Resume. Anthropic credentials stay server-side.
- Persist every successful window's returned signals and full job response to the existing Postgres tables; do not average the windows into one reading.

- Saving a live conversation shows the complete persisted voice/Claude history and a text composer in the same overlay. Continue via real Claude text requests with prompt caching, automatically saving messages; never restart microphone capture. Retain the saved check-in ID in parent state for reopening in the current page. Include final unsent speech once, without generating a reply on Save. Keep the scripted demo separate.

## apps/api/ — Commands

Setup (once): `cd apps/api && cp .env.example .env` (set `APP_API_TOKEN`; Amplifier keys optional — falls back to a mock).

Run from `apps/api/`:

- `docker compose up --build` — runs the API against Postgres at `http://127.0.0.1:8000`.
- Without Docker: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload`.
- `pytest` — runs the test suite (`tests/api/`, `tests/services/`, `tests/core/`, mirroring `app/`).

## Live processing and notifications

- Keep the deployment single-process. Audio buffers, pause gates, notification subscribers,
  single-use tickets, and text-turn locks are process-local; Postgres is authoritative.
- AMPLIFIER completion arrives through signed webhooks. Never add automatic status polling
  or saved-screen refresh intervals. The explicit `analysis/refresh` action is the only
  provider-status GET path. Local microphone timers and transcription scheduling are allowed.
- Publish notifications only after committed state changes. Subscribe before reading the
  initial snapshot and use one socket sender. Webhook inbox application and result/signal
  claims must remain transactional and idempotent; queued retries count as pending work.
- `recording_completed_at` enables text chat; `completed_at` includes terminal analysis.
  Saving and reconnecting notifications must never restart microphone capture.
- The optional Compose `webhooks` profile runs ngrok with a POST-only webhook policy.
  Keep its domain/token in ignored `.env` files and its inspector on host localhost.
- Tests explicitly disable external credentials. Postgres tests use a unique temporary
  schema through `TEST_POSTGRES_URL`; never run destructive tests on public tables.
