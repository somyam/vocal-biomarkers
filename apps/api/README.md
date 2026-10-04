## Run Agent

1. Copy `.env.example` to `.env`.
2. From this directory, run `docker compose up --build` (or, without Docker,
   create a Python venv, install `requirements.txt`, and run
   `uvicorn app.main:app --reload`).
3. The API is then available at `http://127.0.0.1:8000`. Set the React app's
   `VITE_VOCAL_API_URL` and `VITE_VOCAL_API_TOKEN` to point to it.

## Protocol

Pulse receives a WAV submission every 15 seconds of captured audio, containing the
latest up to 30 seconds: 0–15, 0–30, 15–45, 30–60, and so on. Paused time
does not advance this schedule. Save does not submit an extra partial window: a
46-second recording produces exactly three submissions (at 15, 30, and 45 seconds),
while the complete 46-second WAV is saved. Recordings shorter than 15 seconds
are saved and transcribed without analysis. Windows are submitted to the group-aware longitudinal endpoint
(`POST /v2/models/pulse/groups/{group_id}/analyze/longitudinal`) rather than a one-off
score. `group_id` is derived per-user (`user-<user_id>`, see `pulse_group_id` in
`app/services/amplifier.py`) — a longitudinal group represents exactly one subject, so groups are
never shared across members.

The FastAPI service accepts 16 kHz mono signed-16-bit PCM through an authenticated,
one-use WebSocket session. It writes the complete normalized WAV, Pulse jobs, the final
Pulse JSON payload, and a transcript of the recording to Postgres.

## Data model
The backend has these postgres tables: `users`, `checkins`, `recordings`,
`amplifier_jobs`, `analysis_windows`, `amplifier_webhook_inbox`, `checkin_signals`,
`conversation_turns`, `conversation_text_turns`, `interventions`, and `user_interventions`. The latter
records which interventions the private MVP user is currently doing. `checkin_signals`
holds one row per returned signal per successful window (so the same signal can
appear several times within one check-in), including the longitudinal fields
(`baseline_score`, `deviation_from_baseline`, `anomaly`, `z_score`, `population_z`). Those
are `null` until the subject's group has an established baseline.
Gate any trend or intervention-effect analysis on `baseline_score is not None`.

`checkins.transcript` holds a local speech-to-text transcription of the check-in's full
recording (faster-whisper, `WHISPER_MODEL` default `base`) — the authoritative pass runs
once, over the whole clip, at `checkin.end`. While recording, the same clip-so-far is also
re-transcribed on an independent timer (`PARTIAL_TRANSCRIPT_INTERVAL_SECONDS`,
default 3 seconds) and streamed to the client as `transcript_partial` for a live preview; those partial passes are never persisted
and never gate completion — only the final `checkin.end` pass writes `checkin.transcript`.


## Pause and resume

Pause stops and releases browser microphone tracks, drops queued audio frames, and
freezes captions and the recording timer. Resume reacquires the microphone for the
same check-in; permission failure leaves it paused. Captured-audio offsets continue
from where recording stopped.

The backend cancels pending live transcript previews and suppresses their late
results. Every new AMPLIFIER upload, upload PUT, analyze request, and retry
waits while paused. Requests already received by AMPLIFIER may finish remotely;
pause cannot retract them. Save explicitly releases pending analysis work and runs
final transcription on already captured audio, without reopening the microphone.

## Persistence and tracing

Results are persisted as they arrive. `amplifier_jobs.raw_response` holds the full
provider response, and `checkin_signals` holds every returned signal, including
nullable longitudinal fields. A transactional terminal claim ensures concurrent
webhook delivery and explicit recovery insert signals only once per job.

`amplifier_webhook_inbox` durably retains the first valid terminal callback for a
job ID, including callbacks arriving before submission registration. Registration
and startup reconcile unapplied inbox entries. Duplicate callbacks are acknowledged
without inserting signals or scheduling retries twice. Invalid signatures return
401; invalid terminal payloads return 400; database failures return 5xx for retry.

`analysis_windows` persists offsets, pending work, attempt counts, the current job
ID, and temporary WAV bytes needed for bounded retries (two attempts by default).
A failed result and its queued retry commit together; queued retries remain pending
and respect the live pause gate. Terminal windows release their temporary audio.
Upload/submission failures create terminal local-failure records. A restart during
an uncertain submission marks it failed rather than blindly submitting again.
Known accepted jobs remain pending for webhooks; queued retries resume on startup.

Save writes the full WAV to `recordings`, transcribes the recording and final speech,
and sets `recording_completed_at` and duration. Text chat becomes available then,
without waiting for AMPLIFIER. `completed_at` still means recording finalization
and all analysis work reached terminal outcomes. `pulse_json` collects job responses.
Transcription failure remains visible in history and does not block chat indefinitely.

`analysis_status` is `pending`, `complete`, `failed`, or `delayed`. A single deadline
notification marks outstanding work delayed after five minutes; it makes no provider
request. Late signed callbacks still apply. Missing callbacks never fabricate a
terminal result. `POST /v1/checkins/{id}/analysis/refresh` checks each outstanding
job once, only when explicitly requested, and returns a snapshot plus
`analysis_refresh_errors`. It requires bearer auth/ownership and rejects paused
recordings. A failed check leaves the job pending. No timer or reconnect calls it.

Startup creates the additive tables and runs the idempotent
`app/core/migrations.py` migration, adding nullable `checkins.recording_completed_at`
and backfilling it from existing `completed_at` values. Existing records are retained.

The `analyzing` and `job_result` audio WebSocket events include window offsets.
Run **one API process/worker**: notification subscriptions, tickets, stream pause
gates, and text locks are in memory. Postgres holds jobs and conversation history.
Unsaved microphone buffers are not recoverable after an API restart.

## Notifications

- `POST /v1/checkins/{id}/events-ticket`: authenticated, ownership checked; returns
  `events_path` with a short-lived, single-use ticket. Audio tickets cannot authorize it.
- `WS /v1/checkins/{id}/events?ticket=...`: sends
  `{"type":"checkin.snapshot","sequence":0,"checkin":{...}}`, then fresh snapshots
  after committed recording, analysis, and conversation changes. Sequence numbers
  increase per connection. The subscription is registered before the first snapshot;
  one sender serializes delivery, and queued notifications coalesce into fresh reads.
- The saved screen reconnects with a fresh ticket and bounded exponential backoff
  (five consecutive failures, up to eight seconds), then offers manual Reconnect.
  Reconnection recovers state from Postgres without microphone capture or message retries.
  HTTP text submissions keep their original request IDs on explicit retry.

There is no saved-screen refresh interval and no AMPLIFIER status polling loop.
Local recording timers and Whisper preview scheduling remain unchanged.

## Local webhook setup

1. Create an [ngrok account](https://dashboard.ngrok.com/signup), copy its authtoken,
   and obtain your static development domain from the ngrok dashboard.
2. Set these values only in the ignored `apps/api/.env`:

   ```dotenv
   WEBHOOK_BASE_URL=https://your-static-domain.ngrok-free.app
   NGROK_AUTHTOKEN=your-ngrok-authtoken
   AMPLIFIER_WEBHOOK_SECRET=your-long-random-signing-secret
   ```

   Generate a signing secret with `python -c "import secrets; print(secrets.token_hex(32))"`.
   Set AMPLIFIER account/API credentials as usual. Keep keys out of frontend env files.
3. Run `docker compose --profile webhooks up --build -d` from this directory.
   The optional ngrok service forwards to `api:8000`. Its inspector is bound on the
   host only at `http://127.0.0.1:4040`.
4. Record at least 15 seconds and Save. In the inspector, verify a signed
   `POST /v1/webhooks/amplifier` callback and a 200 response. The saved screen should
   receive the result without a history refresh request. Inspect jobs/signals in Postgres.
   A public GET or any other public path must be denied by the traffic policy.

Each longitudinal submission supplies `webhook_url` and `webhook_secret_key` using
the existing audio-upload flow. The backend verifies hex HMAC-SHA256 in
`X-Webhook-Signature` over the unmodified request body. Real submissions reject
missing/invalid HTTPS webhook settings before uploading audio; they never silently
switch to polling. With AMPLIFIER credentials absent, deterministic mock results
work without ngrok. Stop only the tunnel with `docker compose --profile webhooks stop ngrok`.

See ngrok's [agent configuration](https://ngrok.com/docs/gateway/agent/config/v3)
and [deny traffic policy](https://ngrok.com/docs/gateway/traffic-policy/actions/deny).
The committed policy allows only POST to the webhook path; app auth and signature
verification remain the backend's responsibility.

## Tests

Run `python -m pytest -q` from this directory. Tests disable real AMPLIFIER
credentials and use deterministic responses and mock transcription. By default,
they create an isolated temporary SQLite database.

To verify Postgres transactions, set `TEST_POSTGRES_URL` to a test-capable Postgres
connection URL before running the same command. The suite creates a uniquely named
schema, uses it exclusively, and drops it afterward; it does not modify public
tables. Tests cover window boundaries, pause/resume, full recording persistence,
signal fields, retries, duplicate concurrent delivery, rollback, early/late webhooks, notification
authorization and connection races, bounded retries, deadlines, and explicit recovery.

## Sonnet conversation turns

The live recorder shows **Save Conversation** and **End Turn**. End Turn sends
`checkin.turn.end` over the existing authenticated audio WebSocket, after any
previous PCM frames. It pauses the microphone and AMPLIFIER activity, transcribes
only the new turn, and sends the text plus earlier successful turns to Anthropic's
Messages API. The microphone remains paused when the reply arrives; Resume starts
the next voice turn. This request is an explicit exception to the paused-work gate.
Save Conversation still finalizes the complete recording and transcript.

Set server-side `ANTHROPIC_API_KEY` (`ANTHROPIC_API` is also accepted) and optionally
`ANTHROPIC_MODEL` (default `claude-sonnet-5-5`). The key is never sent to the browser.
No Anthropic request is made by ordinary Pause or Save. Sonnet does not wait for
AMPLIFIER results and receives the transcript, not audio or biomarker scores.

Each request enables automatic prompt caching with top-level
`cache_control: {"type": "ephemeral", "ttl": "5m"}`. The unchanged system prompt
and growing message history form the cached prefix. Anthropic Messages still
requires the complete history on every request; the server reconstructs it from
successful `conversation_turns` in this check-in, not a provider response-ID chain.
Cache expiry never loses conversation history. Sonnet 5.5 requires at least 512
prefix tokens to cache; short prompts work normally without a cache hit. We do not
pad prompts or issue background keep-alive requests. See
[Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

WebSocket events: `turn_processing`, `turn_transcript` (`text`), `turn_result`
(`turn_id`, `transcript`, `reply`, `model`, `usage`), or `error` with code
`conversation_failed`. Failed turns can be retried without duplicating the turn
row; concurrent End Turn requests are ignored while one is pending.

The additive `conversation_turns` table stores each turn's audio sample boundaries,
transcript, reply, model, processing status, safe error, and full provider response.
It is created by the existing startup table creation; existing tables are unchanged.
Check-in REST responses include `conversation_turns` for retrieving the saved
exchange. Save retains the original full WAV and final user transcript as before.
Cache usage appears in the developer trace, in REST turn `usage`, and in the full
provider JSON. Inspect the actual counters in Postgres (zero reads are normal on
the first request, for short conversations, or after cache expiry):

```sql
SELECT checkin_id, turn_id, status, model,
       raw_response->>'id' AS provider_message_id,
       raw_response->'usage'->>'cache_creation_input_tokens' AS cache_write_tokens,
       raw_response->'usage'->>'cache_read_input_tokens' AS cache_read_tokens,
       created_at
FROM conversation_turns
ORDER BY created_at DESC
LIMIT 20;
```

## Saved history and text continuation

Save Conversation now displays the complete persisted exchange and a text composer.
The API preserves each successful voice transcript and Claude reply. Any speech
since the last successful End Turn becomes a user-only `conversation_turns` row
with status `saved`; a failed transcription uses `transcription_failed` and a safe
error. Failed audio attempts covered by a later successful/saved span are omitted
from display. The full recording transcript remains a separate artifact and is not
appended to the turn history. Save itself never calls Claude.

Check-in responses now include ordered `conversation_messages` with stable `id`,
`role` (`user` or `assistant`), `text`, `status`, optional `error`, and `request_id`
for typed user messages. The first message is the existing UI opening question.
Older recordings without per-turn rows fall back to the full saved transcript.

`POST /v1/checkins/{checkin_id}/messages` accepts:

```json
{"request_id": "a-client-generated-UUID", "text": "My next message"}
```

This endpoint requires the existing bearer authentication, check-in ownership,
and `recording_completed_at` (analysis may still be pending). Text is trimmed and limited to 10,000
characters. It returns the updated check-in, including history. A provider failure
returns the saved user message with status `failed` and a safe error; retry the
same request ID and text. A completed duplicate returns the existing result.
Reusing an ID for different text, sending before recording finalization, or sending
a different message while an earlier one needs retry returns HTTP 409.

The additive `conversation_text_turns` table stores the request ID, check-in ID,
text, reply, status, timestamps, model, error, and complete Claude response (including
cache usage). Startup creates this table without changing existing tables. Text
messages are serialized per check-in with an async lock in the current single API
process; use a durable queue/DB claim before scaling to multiple workers. Interrupted
requests are marked failed at startup and can be explicitly retried with their
original request ID. Restart never automatically calls Claude. A process
crash after Claude responds but before DB commit may cause a provider call on retry.

Claude receives the successful voice exchanges, final saved speech, and completed
text exchanges with the same system prompt and five-minute automatic caching.
Microphone capture, audio uploads, and AMPLIFIER submissions do not resume for text
chat. Reopening the saved check-in in the current page reloads history from the API;
there is no new all-conversations browser or cross-refresh selection storage.
