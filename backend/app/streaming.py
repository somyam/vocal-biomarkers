"""Transient PCM buffering for the intentionally small prototype schema."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from .amplifier import PulseClient
from .audio import AudioBucketer, AudioChunk, pcm_to_wav
from .database import SessionLocal
from .models import AmplifierJob, CheckIn, Recording


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
        await self.emit("processing", elapsed_seconds=round(self.bucketer.seconds, 2))
        if not any(not task.done() for task in self.processing_tasks):
            await refresh_checkin(self.checkin_id, self)


async def process_chunk(checkin_id: str, chunk: AudioChunk, stream: StreamSession | None = None) -> None:
    client = PulseClient()
    try:
        for attempt in range(client.s.pulse_max_attempts):
            submission = await client.submit(chunk.wav_bytes)
            job_id = str(submission.get("job_id") or submission.get("id") or uuid.uuid4())
            with SessionLocal() as db:
                db.add(AmplifierJob(job_id=job_id, checkin_id=checkin_id,
                    status=str(submission.get("status", "queued")), raw_response=submission))
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


async def apply_job_result(job_id: str, result: dict[str, Any], stream: StreamSession | None = None) -> bool:
    with SessionLocal() as db:
        job = db.get(AmplifierJob, job_id)
        if job is None or job.completed_at is not None:
            return False
        job.status = str(result.get("status", "done"))
        job.raw_response = result
        job.errors = None if job.status == "done" else result
        job.completed_at = now()
        checkin_id = job.checkin_id
        db.commit()
    await refresh_checkin(checkin_id, stream)
    return True


async def refresh_checkin(checkin_id: str, stream: StreamSession | None = None) -> None:
    if stream is not None and not stream.finalized:
        return
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        recording = db.scalar(select(Recording).where(Recording.checkin_id == checkin_id))
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)))
        if checkin is None or recording is None or not jobs:
            return
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
