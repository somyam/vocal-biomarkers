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
`amplifier_jobs`, `checkin_signals`, `interventions`, and `user_interventions`. The latter
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
results. Every new AMPLIFIER upload, upload PUT, analyze request, retry, and job poll
waits while paused. Requests already received by AMPLIFIER may finish remotely;
pause cannot retract them. Save explicitly releases pending analysis work and runs
final transcription on already captured audio, without reopening the microphone.

## Persistence and tracing

Results are persisted as they arrive: `amplifier_jobs.raw_response` holds the full
job response, and `checkin_signals` holds its individual readings. Job status and
signals commit in one transaction; concurrent polling and webhook delivery cannot
insert the same job's signals twice. Each failed attempt remains terminal even
when another attempt is made. A polling error marks the original job failed and
preserves its submission response and error details.

Save writes the complete WAV to `recordings`. Once all window tasks and final
transcription finish, `checkins` receives its duration, transcript, completion time,
and collected job responses in `pulse_json`. The WebSocket wait timeout leaves
processing running in the API process; it does not cancel accepted jobs. This is
still an in-process prototype queue, not a durable worker across API restarts.

The `analyzing` and `job_result` WebSocket events include `start_seconds` and
`end_seconds` alongside the chunk and job IDs. The live developer trace displays
these offsets. No database schema changes are required.

## Tests

Run `python -m pytest -q` from this directory. Tests disable real AMPLIFIER
credentials and use deterministic responses and mock transcription. By default,
they create an isolated temporary SQLite database.

To verify Postgres transactions, set `TEST_POSTGRES_URL` to a test-capable Postgres
connection URL before running the same command. The suite creates a uniquely named
schema, uses it exclusively, and drops it afterward; it does not modify public
tables. Tests cover window boundaries, pause/resume, full recording persistence,
signal fields, retries, duplicate concurrent delivery, rollback, and timeouts.

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
and completed recording finalization. Text is trimmed and limited to 10,000
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
requests can be retried with their original request ID after a restart. A process
crash after Claude responds but before DB commit may cause a provider call on retry.

Claude receives the successful voice exchanges, final saved speech, and completed
text exchanges with the same system prompt and five-minute automatic caching.
Microphone capture, audio uploads, and AMPLIFIER submissions do not resume for text
chat. Reopening the saved check-in in the current page reloads history from the API;
there is no new all-conversations browser or cross-refresh selection storage.
