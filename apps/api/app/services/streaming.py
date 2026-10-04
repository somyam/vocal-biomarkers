"""Transient PCM buffering for the intentionally small prototype schema."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select, update

from ..core.config import settings
from ..core.database import SessionLocal
from ..models import AmplifierJob, CheckIn, CheckInSignal, Recording
from .amplifier import TERMINAL, PulseClient, pulse_group_id
from .audio import AudioBucketer, AudioChunk, pcm_to_wav
from .conversation import process_conversation_turn
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
    processing_complete: bool = False
    finalization_task: asyncio.Task[None] | None = None
    processing_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    # Live partial transcription: re-transcribes the whole clip so far on its own timer
    # (partial_transcript_interval_seconds), decoupled from Amplifier's hop cadence, kept
    # out of `processing_tasks` so a still-running partial pass never delays `finalize()`'s
    # wait on the real, authoritative transcript.
    transcribing_partial: bool = False
    partial_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    partial_loop_task: asyncio.Task[None] | None = None
    active_event: asyncio.Event = field(default_factory=asyncio.Event)
    transcript_generation: int = 0
    turn_start_sample: int = 0
    turn_task: asyncio.Task[None] | None = None

    async def emit(self, event: str, **payload: Any) -> None:
        if self.socket is None:
            return
        try:
            await self.socket.send_json({"type": event, "checkin_id": self.checkin_id, **payload})
        except Exception:
            self.socket = None

    async def start(self) -> None:
        self.started, self.paused = True, False
        self.active_event.set()
        await self.emit("recording", state="recording", elapsed_seconds=0)
        if self.partial_loop_task is None:
            self.partial_loop_task = asyncio.create_task(self._partial_transcript_loop())

    async def pause(self) -> None:
        self.paused = True
        self.active_event.clear()
        self.transcript_generation += 1
        pending = [task for task in self.partial_tasks if not task.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self.transcribing_partial = False
        await self.emit("recording", state="paused", elapsed_seconds=round(self.bucketer.seconds, 2))

    async def resume(self) -> None:
        if self.turn_task is not None and not self.turn_task.done():
            await self.emit("error", code="turn_in_progress", message="Please wait for the coach's reply before resuming.")
            return
        self.paused = False
        self.active_event.set()
        await self.emit("recording", state="recording", elapsed_seconds=round(self.bucketer.seconds, 2))

    async def wait_until_active(self) -> None:
        while self.paused:
            await self.active_event.wait()

    async def end_turn(self) -> None:
        if self.finalized or not self.started:
            await self.emit("error", code="conversation_failed", message="Start a recording before ending a turn.")
            return
        if self.turn_task is not None and not self.turn_task.done():
            return
        await self.pause()
        end_sample = len(self.bucketer.buffer) // 2
        if end_sample <= self.turn_start_sample:
            await self.emit("error", code="conversation_failed", message="Resume speaking before ending another turn.")
            return
        self.turn_task = asyncio.create_task(process_conversation_turn(self, self.turn_start_sample, end_sample))
        self.processing_tasks.append(self.turn_task)

    async def ingest(self, pcm: bytes) -> None:
        if not self.started or self.paused or self.finalized:
            return
        if len(pcm) % 2:
            await self.emit("error", code="invalid_pcm_frame", message="Audio frames must contain signed 16-bit PCM samples.")
            return
        chunks = self.bucketer.feed(pcm)
        for chunk in chunks:
            self._queue_pulse_job(chunk)
        await self.emit("recording", state="recording", elapsed_seconds=round(self.bucketer.seconds, 2))

    def _queue_pulse_job(self, chunk: AudioChunk) -> None:
        self.processing_tasks.append(asyncio.create_task(process_chunk(self.checkin_id, chunk, self)))

    def _queue_partial_transcript(self) -> None:
        # Skip if a previous pass hasn't finished -- the next timer tick's audio will
        # include this one anyway, so nothing is lost by waiting rather than stacking
        # concurrent Whisper calls on top of each other.
        if self.transcribing_partial or self.paused or self.finalized:
            return
        self.transcribing_partial = True
        self.partial_tasks.append(asyncio.create_task(partial_transcribe(self)))

    async def _partial_transcript_loop(self) -> None:
        """Independent timer driving live transcript previews, so they update on
        `partial_transcript_interval_seconds` rather than waiting on Amplifier's
        30s/15s hop cadence (see AudioBucketer)."""
        interval = settings().partial_transcript_interval_seconds
        while not self.finalized:
            await asyncio.sleep(interval)
            if self.finalized:
                break
            if self.started and not self.paused and self.bucketer.seconds > 0:
                self._queue_partial_transcript()

    async def finalize(self) -> None:
        if self.finalized:
            return
        self.finalized, self.paused = True, False
        self.active_event.set()  # Save explicitly permits finishing previously queued work.
        self.transcript_generation += 1
        if self.partial_loop_task is not None:
            self.partial_loop_task.cancel()
        for task in self.partial_tasks:
            task.cancel()
        for chunk in self.bucketer.flush():
            self._queue_pulse_job(chunk)
        wav = pcm_to_wav(bytes(self.bucketer.buffer), self.bucketer.sample_rate)
        with SessionLocal() as db:
            if not db.scalar(select(Recording).where(Recording.checkin_id == self.checkin_id)):
                db.add(Recording(checkin_id=self.checkin_id, user_id=self.user_id, audio_wav=wav))
                db.commit()
        # The authoritative, persisted transcript -- one final pass over the whole clip.
        # `partial_transcribe` already streamed live, unpersisted previews during
        # recording (see `_queue_partial_transcript`); this is the pass that actually
        # writes `checkin.transcript`. Runs concurrently with the queued Amplifier jobs
        # via the same wait/timeout below.
        self.processing_tasks.append(asyncio.create_task(transcribe_checkin(self.checkin_id, wav, self)))
        await self.emit("processing", elapsed_seconds=round(self.bucketer.seconds, 2))
        # A socket timeout must not cancel accepted jobs or the final transcript.
        # Keep ownership of the background task until all persistence is finished.
        self.finalization_task = asyncio.create_task(self._finish_processing())
        try:
            await asyncio.wait_for(
                asyncio.shield(self.finalization_task),
                timeout=settings().finalize_timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self.emit("error", code="processing_timeout",
                message="Your check-in is taking longer than expected to process. "
                        "Check back shortly for the result.")

    async def _finish_processing(self) -> None:
        await asyncio.gather(*self.processing_tasks, return_exceptions=True)
        from .conversation import save_final_speech
        await save_final_speech(self)
        self.processing_complete = True
        await refresh_checkin(self.checkin_id, self)
        streams.remove(self.checkin_id)


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
        client.wait_until_active = stream.wait_until_active
    # The real endpoint being called, group_id baked in -- shown verbatim in the
    # "analyzing" event below rather than a generic placeholder, so "behind the
    # scenes" shows the actual request, not a stylized description of one.
    endpoint = f"/v2/models/pulse/groups/{group_id}/analyze/longitudinal"
    job_id: str | None = None
    try:
        for attempt in range(max(1, client.s.pulse_max_attempts)):
            job_id = None
            if stream:
                await stream.wait_until_active()
            submission = await client.submit(group_id, chunk.wav_bytes, recorded_at_str)
            job_id = str(submission.get("job_id") or submission.get("id") or uuid.uuid4())
            with SessionLocal() as db:
                db.add(AmplifierJob(job_id=job_id, checkin_id=checkin_id, group_id=group_id,
                    recorded_at=recorded_at, status=str(submission.get("status", "queued")).lower(),
                    raw_response=submission))
                db.commit()
            if stream:
                await stream.emit("analyzing", chunk=chunk.index, job_id=job_id, method="POST", path=endpoint,
                    start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds)
            if stream:
                await stream.wait_until_active()
            result = submission if str(submission.get("status", "")).lower() in TERMINAL else await client.wait_for_result(job_id)
            status = str(result.get("status", "")).lower()
            if status not in TERMINAL:
                raise ValueError("AMPLIFIER returned a nonterminal result")
            # Every attempt remains terminal, including attempts that will be retried.
            # A 'retrying' row would otherwise block check-in completion forever.
            await apply_job_result(job_id, result, stream)
            if status in {"failed", "timed-out"}:
                if attempt + 1 < client.s.pulse_max_attempts:
                    continue
                if stream:
                    await stream.emit("error", code="pulse_processing_failed", message="We could not analyze this audio.")
            elif stream:
                signals = (result.get("result") or {}).get("signals") or []
                await stream.emit("job_result", chunk=chunk.index, job_id=job_id,
                    start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds,
                    signals=[{"name": s.get("name"), "level": s.get("level")} for s in signals])
            return
    except Exception as exc:
        with SessionLocal() as db:
            if job_id is not None:
                # Preserve the accepted submission and mark that same row failed,
                # unless a concurrent webhook has already completed it.
                db.execute(update(AmplifierJob).where(
                    AmplifierJob.job_id == job_id, AmplifierJob.completed_at.is_(None),
                ).values(status="failed", errors={"message": str(exc)}, completed_at=now()))
            else:
                db.add(AmplifierJob(job_id=f"local-failure-{uuid.uuid4()}", checkin_id=checkin_id,
                    group_id=group_id, recorded_at=recorded_at, status="failed",
                    errors={"message": str(exc)}, completed_at=now()))
            db.commit()
        if stream:
            await stream.emit("error", code="pulse_processing_failed", message="We could not analyze this audio.")
        await refresh_checkin(checkin_id, stream)


async def partial_transcribe(stream: StreamSession) -> None:
    """Best-effort live preview: re-transcribes the whole clip recorded so far and emits
    it as `transcript_partial`. Never touches the database and never blocks on failure --
    the single authoritative pass in `transcribe_checkin` at `checkin.end` is what actually
    gets persisted to `checkin.transcript`."""
    generation = stream.transcript_generation
    try:
        if stream.paused or stream.finalized:
            return
        wav = pcm_to_wav(bytes(stream.bucketer.buffer[stream.turn_start_sample * 2:]), stream.bucketer.sample_rate)
        text = await transcriber().transcribe(wav)
        if text and not stream.paused and not stream.finalized and generation == stream.transcript_generation:
            await stream.emit("transcript_partial", text=text)
    except Exception:
        pass
    finally:
        stream.transcribing_partial = False


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
    status = str(result.get("status", "")).lower()
    if status not in TERMINAL:
        return False
    with SessionLocal() as db:
        # Atomically claim a terminal result. PostgreSQL serializes competing
        # updates and rechecks completed_at after the winner commits. The claim
        # and all signal inserts commit together, or roll back together.
        claimed = db.execute(update(AmplifierJob).where(
            AmplifierJob.job_id == job_id, AmplifierJob.completed_at.is_(None),
        ).values(status=status, raw_response=result,
            errors=None if status == "done" else result, completed_at=now()
        ).returning(AmplifierJob.checkin_id, AmplifierJob.recorded_at)).first()
        if claimed is None:
            return False
        checkin_id, recorded_at = claimed
        checkin = db.get(CheckIn, checkin_id)
        if status == "done" and checkin is not None:
            payload = result.get("result") or {}
            for signal in payload.get("signals") or []:
                db.add(CheckInSignal(
                    checkin_id=checkin_id, user_id=checkin.user_id,
                    signal_name=str(signal.get("name", "")),
                    recorded_at=recorded_at or now(),
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
    stream = stream or streams.sessions.get(checkin_id)
    if stream is not None and not stream.processing_complete:
        return
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is not None and checkin.completed_at is not None:
            return  # already finalized by an earlier call — avoid recomputing / re-emitting "result"
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)
            .order_by(AmplifierJob.recorded_at, AmplifierJob.created_at, AmplifierJob.job_id)))
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
