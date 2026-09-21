"""Live PCM check-in sessions and asynchronous Pulse processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from .amplifier import PulseClient, quality_view, trend_view
from .audio import AudioBucketer, AudioChunk, pcm_to_wav
from .database import SessionLocal
from .models import AmplifierJob, CheckIn, CheckInSegment, HabitCompletion, Recording


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
        with SessionLocal() as db:
            checkin = db.get(CheckIn, self.checkin_id)
            if checkin:
                checkin.status = "recording"
                checkin.started_at = checkin.started_at or now()
                db.commit()
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
            await self._queue_segment(chunk)
        await self.emit("recording", state="recording", elapsed_seconds=round(self.bucketer.seconds, 2))

    async def _queue_segment(self, chunk: AudioChunk) -> None:
        with SessionLocal() as db:
            segment = CheckInSegment(checkin_id=self.checkin_id, sequence=chunk.index,
                start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds,
                wav_bytes=chunk.wav_bytes, status="queued")
            db.add(segment)
            db.commit()
            segment_id = segment.id
        await self.emit("queued", segment_index=chunk.index,
            start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds)
        self.processing_tasks.append(asyncio.create_task(process_segment(self.checkin_id, segment_id, self)))

    async def finalize(self) -> None:
        if self.finalized:
            return
        self.finalized, self.paused = True, False
        for chunk in self.bucketer.flush():
            await self._queue_segment(chunk)
        duration = self.bucketer.seconds
        wav = pcm_to_wav(bytes(self.bucketer.buffer), self.bucketer.sample_rate)
        with SessionLocal() as db:
            checkin = db.get(CheckIn, self.checkin_id)
            if not checkin:
                return
            checkin.status, checkin.duration_seconds, checkin.finished_at = "processing", duration, now()
            recording = db.scalar(select(Recording).where(Recording.checkin_id == self.checkin_id))
            if recording is None:
                db.add(Recording(checkin_id=self.checkin_id, wav_bytes=wav,
                    sample_rate=self.bucketer.sample_rate, duration_seconds=duration))
            completion = db.scalar(select(HabitCompletion).where(HabitCompletion.checkin_id == self.checkin_id))
            if completion is None:
                db.add(HabitCompletion(checkin_id=self.checkin_id, habit_name="Morning Check-in"))
            db.commit()
        await self.emit("processing", state="processing", elapsed_seconds=round(duration, 2))
        if not any(not task.done() for task in self.processing_tasks):
            await refresh_checkin(self.checkin_id, self)


async def process_segment(checkin_id: str, segment_id: str, stream: StreamSession | None = None) -> None:
    with SessionLocal() as db:
        segment = db.get(CheckInSegment, segment_id)
        if segment is None:
            return
        segment.status = "processing"
        db.commit()
        wav = segment.wav_bytes
    if stream:
        await stream.emit("processing", segment_id=segment_id)
    client = PulseClient()
    try:
        for attempt in range(client.s.pulse_max_attempts):
            submission = await client.submit(wav)
            provider_job_id = str(submission.get("job_id") or submission.get("id") or f"{segment_id}-{attempt}")
            with SessionLocal() as db:
                job = AmplifierJob(checkin_id=checkin_id, segment_id=segment_id,
                    provider_job_id=provider_job_id, status=str(submission.get("status", "queued")),
                    raw_response=submission)
                db.add(job)
                db.commit()
            result = submission if submission.get("status") == "done" else await client.wait_for_result(provider_job_id)
            if str(result.get("status", "")).lower() in {"failed", "timed-out"} and attempt + 1 < client.s.pulse_max_attempts:
                with SessionLocal() as db:
                    previous = db.scalar(select(AmplifierJob).where(AmplifierJob.provider_job_id == provider_job_id))
                    if previous:
                        previous.status, previous.raw_response, previous.error, previous.completed_at = "retrying", result, result, now()
                        db.commit()
                if stream:
                    await stream.emit("processing", segment_id=segment_id, retrying=True)
                continue
            await apply_job_result(provider_job_id, result, stream)
            break
    except Exception as exc:
        with SessionLocal() as db:
            segment = db.get(CheckInSegment, segment_id)
            if segment:
                segment.status = "failed"
            job = db.scalar(select(AmplifierJob).where(AmplifierJob.segment_id == segment_id))
            if job:
                job.status, job.error, job.completed_at = "failed", {"message": str(exc)}, now()
            db.commit()
        if stream:
            await stream.emit("error", code="pulse_processing_failed", message="We could not analyze this segment. Please try again.")
        await refresh_checkin(checkin_id, stream)


async def apply_job_result(provider_job_id: str, result: dict[str, Any], stream: StreamSession | None = None) -> bool:
    """Apply a webhook or polling result exactly once."""
    with SessionLocal() as db:
        job = db.scalar(select(AmplifierJob).where(AmplifierJob.provider_job_id == provider_job_id))
        if job is None:
            return False
        terminal = {"done", "failed", "timed-out"}
        incoming_status = str(result.get("status", "done"))
        if job.status in terminal and job.completed_at is not None:
            return False
        job.status, job.raw_response = incoming_status, result
        job.completed_at = now() if incoming_status in terminal else None
        if incoming_status != "done":
            job.error = result
        segment = db.get(CheckInSegment, job.segment_id)
        if segment:
            segment.status = incoming_status
        checkin_id = job.checkin_id
        db.commit()
    await refresh_checkin(checkin_id, stream)
    return True


async def refresh_checkin(checkin_id: str, stream: StreamSession | None = None) -> None:
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None or checkin.status != "processing":
            return
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)))
        if checkin.duration_seconds < 60:
            checkin.status = "needs_rerecord"
            checkin.quality_result = {"status": "needs_rerecord", "message": "Talk for at least 1 minute for a complete check-in."}
            checkin.completed_at = now()
            event, payload = "quality", checkin.quality_result
        elif not jobs:
            checkin.status = "needs_rerecord"
            checkin.quality_result = {"status": "needs_rerecord", "message": "Record at least 20 seconds of audio."}
            event, payload = "quality", checkin.quality_result
        elif any(job.status not in {"done", "failed", "timed-out"} for job in jobs):
            return
        else:
            successful = [job.raw_response or {} for job in jobs if job.status == "done"]
            if not successful:
                checkin.status = "failed"
                checkin.quality_result = {"status": "unavailable", "message": "Your check-in was saved, but analysis is unavailable."}
                event, payload = "error", checkin.quality_result
            else:
                quality = quality_view(successful)
                checkin.quality_result = quality
                if quality["status"] == "needs_rerecord":
                    checkin.status, event, payload = "needs_rerecord", "quality", quality
                else:
                    checkin.status = "complete"
                    checkin.pulse_summary = {"segments_analyzed": len(successful)}
                    checkin.trend_summary = trend_view(successful)
                    event, payload = "result", {"quality": quality, "trend": checkin.trend_summary}
            checkin.completed_at = now()
        db.commit()
    if stream:
        await stream.emit(event, **payload)


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
