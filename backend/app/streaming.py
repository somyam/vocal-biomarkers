"""Transient PCM buffering for the intentionally small prototype schema."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from .amplifier import PulseClient, pulse_group_id
from .audio import AudioBucketer, AudioChunk, pcm_to_wav
from .config import settings
from .database import SessionLocal
from .models import AmplifierJob, CheckIn, CheckInSignal, Recording
from .transcribe import transcriber


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StreamSession:
    checkin_id: str
    user_id: str
    socket: WebSocket | None = None
    bucketer: AudioBucketer = field(default_factory=AudioBucketer)
    started: bool = False
    paused: bool = False
    finalized: bool = False
    processing_tasks: list[asyncio.Task[None]] = field(default_factory=list)

    async def emit(self, event: str, **payload: Any) -> None:
        if self.socket is None:
            return
        try:
            await self.socket.send_json({"type": event, "checkin_id": self.checkin_id, **payload})
        except Exception:
            self.socket = None

    async def start(self) -> None:
        self.started, self.paused = True, False
        await self.emit("recording", state="recording", elapsed_seconds=0)

    async def pause(self) -> None:
        self.paused = True
        await self.emit("recording", state="paused", elapsed_seconds=round(self.bucketer.seconds, 2))

    async def resume(self) -> None:
        self.paused = False
        await self.emit("recording", state="recording", elapsed_seconds=round(self.bucketer.seconds, 2))

    async def ingest(self, pcm: bytes) -> None:
        if not self.started or self.paused or self.finalized:
            return
        if len(pcm) % 2:
            await self.emit("error", code="invalid_pcm_frame", message="Audio frames must contain signed 16-bit PCM samples.")
            return
        for chunk in self.bucketer.feed(pcm):
            self._queue_pulse_job(chunk)
        await self.emit("recording", state="recording", elapsed_seconds=round(self.bucketer.seconds, 2))

    def _queue_pulse_job(self, chunk: AudioChunk) -> None:
        self.processing_tasks.append(asyncio.create_task(process_chunk(self.checkin_id, chunk, self)))

    async def finalize(self) -> None:
        if self.finalized:
            return
        self.finalized, self.paused = True, False
        for chunk in self.bucketer.flush():
            self._queue_pulse_job(chunk)
        wav = pcm_to_wav(bytes(self.bucketer.buffer), self.bucketer.sample_rate)
        with SessionLocal() as db:
            if not db.scalar(select(Recording).where(Recording.checkin_id == self.checkin_id)):
                db.add(Recording(checkin_id=self.checkin_id, user_id=self.user_id, audio_wav=wav))
                db.commit()
        # One pass over the whole clip, not per-chunk -- a check-in is a single short
        # personal recording, not a two-party encounter needing live partial text. Runs
        # concurrently with the queued Amplifier jobs via the same wait/timeout below.
        self.processing_tasks.append(asyncio.create_task(transcribe_checkin(self.checkin_id, wav, self)))
        await self.emit("processing", elapsed_seconds=round(self.bucketer.seconds, 2))
        # Keep the socket open until every queued chunk's real Amplifier round trip and the
        # transcription both land. The bug was that the handler used to return (and so
        # close the socket) right after queuing these as fire-and-forget tasks, long
        # before a real analyze call could finish, silently dropping the eventual
        # "result"/"error". processing_tasks is never empty here -- the transcription task
        # above is always queued, even for a check-in with no Amplifier chunks at all.
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.processing_tasks, return_exceptions=True),
                timeout=settings().finalize_timeout_seconds,
            )
        except asyncio.TimeoutError:
            # wait_for cancels whatever's still running on timeout; a cancelled Amplifier
            # job may still complete later via webhook (apply_job_result is idempotent
            # either way), but this connection isn't waiting any longer for any of it.
            await self.emit("error", code="processing_timeout",
                message="Your check-in is taking longer than expected to process. "
                        "Check back shortly for the result.")
            return
        # A chunk queued during `ingest()` can finish (and call refresh_checkin) before
        # this point ever creates the Recording row above — most likely when analysis
        # resolves near-instantly (offline/mock mode), unlikely but possible for a very
        # fast real one. Its own refresh_checkin call finds `recording is None` and no-ops
        # by design (not ready yet), so nothing else re-triggers it once the row exists.
        # refresh_checkin is idempotent, so re-running it here — after every task this
        # check-in queued is confirmed done — closes that race unconditionally.
        await refresh_checkin(self.checkin_id, self)


async def process_chunk(checkin_id: str, chunk: AudioChunk, stream: StreamSession | None = None) -> None:
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None:
            return
        user_id = checkin.user_id
        # recorded_at orders this reading within the subject's longitudinal history — the
        # check-in's own start time plus this chunk's offset, not the moment we submit it.
        recorded_at = checkin.started_at + timedelta(seconds=chunk.start_seconds)
    group_id = pulse_group_id(user_id)
    recorded_at_str = recorded_at.isoformat(timespec="seconds") + "Z"
    client = PulseClient()
    if stream:
        await stream.emit("analyzing", chunk=chunk.index)
    try:
        for attempt in range(client.s.pulse_max_attempts):
            submission = await client.submit(group_id, chunk.wav_bytes, recorded_at_str)
            job_id = str(submission.get("job_id") or submission.get("id") or uuid.uuid4())
            with SessionLocal() as db:
                db.add(AmplifierJob(job_id=job_id, checkin_id=checkin_id, group_id=group_id,
                    recorded_at=recorded_at, status=str(submission.get("status", "queued")),
                    raw_response=submission))
                db.commit()
            result = submission if submission.get("status") == "done" else await client.wait_for_result(job_id)
            if str(result.get("status", "")).lower() in {"failed", "timed-out"} and attempt + 1 < client.s.pulse_max_attempts:
                with SessionLocal() as db:
                    job = db.get(AmplifierJob, job_id)
                    if job:
                        job.status, job.raw_response, job.errors, job.completed_at = "retrying", result, result, now()
                        db.commit()
                continue
            await apply_job_result(job_id, result, stream)
            return
    except Exception as exc:
        job_id = f"local-failure-{uuid.uuid4()}"
        with SessionLocal() as db:
            db.add(AmplifierJob(job_id=job_id, checkin_id=checkin_id, status="failed",
                errors={"message": str(exc)}, completed_at=now()))
            db.commit()
        if stream:
            await stream.emit("error", code="pulse_processing_failed", message="We could not analyze this audio.")
        await refresh_checkin(checkin_id, stream)


async def transcribe_checkin(checkin_id: str, wav_bytes: bytes, stream: StreamSession | None = None) -> None:
    """Transcribe a check-in's full recording and persist it, independent of how the
    Amplifier jobs for this same check-in turn out. A failure here still marks
    `transcribed_at` -- like a failed AmplifierJob still reaching a terminal status --
    so refresh_checkin's completion gate isn't left waiting on something that will never
    arrive."""
    text: str | None
    if stream:
        await stream.emit("transcribing")
    try:
        text = await transcriber().transcribe(wav_bytes)
    except Exception:
        text = None
        if stream:
            await stream.emit("error", code="transcription_failed",
                message="We could not transcribe this recording.")
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is not None:
            checkin.transcript = text
            checkin.transcribed_at = now()
            db.commit()
    if stream and text is not None:
        await stream.emit("transcript", text=text)
    await refresh_checkin(checkin_id, stream)


async def apply_job_result(job_id: str, result: dict[str, Any], stream: StreamSession | None = None) -> bool:
    with SessionLocal() as db:
        job = db.get(AmplifierJob, job_id)
        if job is None or job.completed_at is not None:
            return False  # already applied — guards the poll path and the webhook racing each other
        job.status = str(result.get("status", "done"))
        job.raw_response = result
        job.errors = None if job.status == "done" else result
        job.completed_at = now()
        checkin_id = job.checkin_id
        checkin = db.get(CheckIn, checkin_id)
        if job.status == "done" and checkin is not None:
            payload = result.get("result") or {}
            for signal in payload.get("signals") or []:
                db.add(CheckInSignal(
                    checkin_id=checkin_id, user_id=checkin.user_id,
                    signal_name=str(signal.get("name", "")),
                    recorded_at=job.recorded_at or now(),
                    score=float(signal.get("score") or 0.0),
                    level=str(signal.get("level", "")),
                    flagged=bool(signal.get("flagged", False)),
                    latest_score=signal.get("latest_score"),
                    baseline_score=signal.get("baseline_score"),
                    deviation_from_baseline=signal.get("deviation_from_baseline"),
                    anomaly=signal.get("anomaly"),
                    z_score=signal.get("z_score"),
                    population_z=signal.get("population_z"),
                ))
        db.commit()
    await refresh_checkin(checkin_id, stream)
    return True


async def refresh_checkin(checkin_id: str, stream: StreamSession | None = None) -> None:
    if stream is not None and not stream.finalized:
        return
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is not None and checkin.completed_at is not None:
            return  # already finalized by an earlier call — avoid recomputing / re-emitting "result"
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)))
        if checkin is None or recording is None or checkin.transcribed_at is None:
            return  # not ready: recording not written yet, or the transcription
            # attempt (success or failure) hasn't finished. `jobs` may legitimately be
            # empty -- a check-in whose total audio never crossed Amplifier's floor
            # never queues one -- so an empty list no longer blocks completion on its
            # own; by the time we reach this point (past the guard above), whichever
            # code path got us here has already queued every job this check-in will
            # ever have, so an empty list here really does mean "none, permanently."
        if any(job.status not in {"done", "failed", "timed-out"} for job in jobs):
            return
        checkin.duration_seconds = max(0, len(recording.audio_wav) - 44) / (16_000 * 2)
        checkin.completed_at = now()
        checkin.pulse_json = {"jobs": [job.raw_response for job in jobs]}
        db.commit()
    if stream:
        await stream.emit("result", status="complete")


class StreamRegistry:
    def __init__(self) -> None:
        self.sessions: dict[str, StreamSession] = {}

    def create(self, checkin_id: str, user_id: str, socket: WebSocket | None = None) -> StreamSession:
        session = StreamSession(checkin_id=checkin_id, user_id=user_id, socket=socket)
        self.sessions[checkin_id] = session
        return session

    async def finalize(self, checkin_id: str) -> None:
        session = self.sessions.get(checkin_id)
        if session:
            await session.finalize()

    def remove(self, checkin_id: str) -> None:
        self.sessions.pop(checkin_id, None)


streams = StreamRegistry()
