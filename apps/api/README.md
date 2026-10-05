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
`conversation_turns`, `conversation_text_turns`, `conversation_contexts`, `interventions`, and `user_interventions`. The latter
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

ngrok gives the local API a public HTTPS callback address that AMPLIFIER can reach.
It forwards incoming callbacks to `api:8000` on the Compose network. The browser
still connects directly to the local API; audio uploads to AMPLIFIER and requests
to Claude use the backend's existing outgoing connections.

1. Create an [ngrok account](https://dashboard.ngrok.com/signup), copy its authtoken,
   and obtain your static development domain from the ngrok dashboard.
2. Set these values only in the ignored `apps/api/.env`:

   ```dotenv
   WEBHOOK_BASE_URL=https://your-static-domain.ngrok-free.app
   NGROK_AUTHTOKEN=your-ngrok-authtoken
   AMPLIFIER_WEBHOOK_SECRET=your-long-random-signing-secret
   ```

   Generate a signing secret with `python -c "import secrets; print(secrets.token_hex(32))"`.
   Use the exact domain assigned to your account, including its suffix. Set
   `WEBHOOK_BASE_URL` to the HTTPS origin only; the backend appends
   `/v1/webhooks/amplifier`. Keep an existing signing secret when reconfiguring the
   tunnel. Set AMPLIFIER account/API credentials as usual; keep keys out of frontend
   env files and commits.
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

### Managing ngrok in Docker Desktop

After Compose creates the services, open **Containers → api** to find `api-1`,
`db-1`, and `ngrok-1`. Start, stop, and inspect `ngrok-1` there. These names reflect
the default Compose project name; a custom project name changes the grouping.
The separate **Extensions → ngrok** interface is not used by this setup.

Run the Compose startup command again after changing `.env` so the API and tunnel
load the new settings. A simple container restart does not reload environment
variables. Keep the tunnel running while submitted jobs are awaiting callbacks.

If startup reports `ERR_NGROK_334` / “endpoint is already online,” another ngrok
session owns the same domain. Stop that domain's existing tunnel before starting
the project service. For an extension-created endpoint, use **Docker Desktop →
Extensions → ngrok → Set Offline** on the matching endpoint. Do not enable pooling
to resolve this conflict: callbacks could be routed to the wrong backend.

### Inspecting callback delivery

Open [the local ngrok inspector](http://127.0.0.1:4040), select a
`POST /v1/webhooks/amplifier` request, and inspect its job ID, status, JSON body,
and response. The inspector is exposed only on host localhost. Incoming callbacks
also appear in **Docker Desktop → Containers → api → api-1 → Logs**.

| Observation | Meaning |
| --- | --- |
| Webhook POST returns `200` | The backend accepted the callback. Read the payload's `status` to see whether analysis succeeded or failed. Duplicate valid callbacks are also acknowledged. |
| Webhook POST returns `401` | The signature is missing or invalid; check that the configured signing secret matches the secret supplied with the job. |
| Webhook POST returns `400` | The callback body failed terminal-job validation. |
| Public GET or another public path returns `403` | The tunnel's webhook-only traffic policy is working. Use localhost for the app, API health endpoint, and inspector. |
| Analysis stays pending or becomes delayed | Check tunnel connectivity and webhook delivery. Use **Check analysis once** for explicit recovery; no automatic status polling runs. |

Each submitted audio window has its own job and terminal callback. Two successful
webhook POSTs can therefore represent two different windows; compare job IDs before
treating them as duplicates. API access logs show incoming requests, not the
backend's outgoing AMPLIFIER uploads and analysis requests.

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
only the new turn, and sends the text plus earlier successful turns and the saved
historical context to Anthropic's Messages API. The microphone remains paused when
the reply arrives; Resume starts
the next voice turn. This request is an explicit exception to the paused-work gate.
Save Conversation still finalizes the complete recording and transcript.

Set server-side `ANTHROPIC_API_KEY` (`ANTHROPIC_API` is also accepted) and optionally
`ANTHROPIC_MODEL` (default `claude-sonnet-5-5`). The key is never sent to the browser.
No Anthropic request is made by ordinary Pause or Save. Sonnet does not wait for
current AMPLIFIER results. It receives text and available historical biomarker
measurements from the conversation's startup snapshot, never audio.

Each request enables automatic prompt caching with top-level
`cache_control: {"type": "ephemeral", "ttl": "5m"}`. The unchanged system prompt,
fixed historical snapshot, and growing message history form the cached prefix.
Anthropic Messages still
requires the complete history on every request; the server reconstructs it from
successful `conversation_turns` in this check-in, not a provider response-ID chain.
Cache expiry never loses conversation history. Sonnet 5.5 requires at least 512
prefix tokens to cache; short prompts work normally without a cache hit. We do not
pad prompts or issue background keep-alive requests. See
[Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

### Historical context at conversation start

`POST /v1/checkins` creates the check-in and its `conversation_contexts` row in one
transaction. The server selects only the authenticated user's finalized recordings
(`recording_completed_at` is set), ordered by `started_at`: at most 10 from the
preceding 30 days. An unfinished analysis does not block selection or creation.
The opening stays “How are you feeling today?”; the first Claude call still requires
End Turn or a saved text message. This does not add a provider call, polling, or a
new public endpoint. The prototype token currently identifies `mvp-user`.

Each snapshot contains the full `checkins.transcript` once per source recording,
timestamps, duration, and successful non-mock AMPLIFIER job results. Spoken turn
transcripts, prior Claude replies, and earlier text-chat exchanges are not added
again. Analysis uses the persisted job responses to retain per-window provenance:
job/window IDs, audio offsets when available, recorded time, signal scores/levels,
longitudinal fields (including nulls), and audio-quality information. Older jobs
without window metadata retain their job ID and timestamp. Overlapping windows
are never averaged or treated as independent readings. Missing transcripts and
unavailable analysis are marked explicitly; pending/failed job counts remain
visible in the context, but their payloads and provider errors are excluded.

The row's primary key is the check-in ID. It stores `captured_at`, `format_version`,
`source_checkin_ids`, the structured `snapshot`, and exact `rendered_context` text.
The selected source IDs remain for audit even if size limits omit their content.
History is rendered in chronological order with a 60,000-character limit. If
needed, older transcript excerpts are shortened first, followed by omission of
oldest windows, then oldest conversations. The JSON records omitted character,
window, and conversation counts. No extra model call summarizes the history.

Both voice and text replies read the stored text unchanged before the current
exchange. Reopening, retries, restarts, edited source transcripts, and late
webhooks do not rebuild the snapshot. New conversations can use those newer data.
The system prompt labels all historical content as untrusted background, preserves
uncertainty, and distinguishes past measurements from present reports. Snapshot
content stays server-side until sent to Anthropic; it is not added to public
check-in responses or logs. It is stored in Postgres as personal conversation data.

Startup's existing `Base.metadata.create_all` adds this table without altering
existing data. Old conversations without a snapshot keep their original prompt;
there is no automatic backfill. Prompt cache expiry never deletes this history.

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

Claude receives the fixed historical snapshot plus successful voice exchanges,
final saved speech, and completed text exchanges with the same system prompt and
five-minute automatic caching.
Microphone capture, audio uploads, and AMPLIFIER submissions do not resume for text
chat. Reopening the saved check-in in the current page reloads history from the API;
there is no new all-conversations browser or cross-refresh selection storage.
