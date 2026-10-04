"""Transient PCM buffering for the intentionally small prototype schema."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select

from ..core.config import settings
from ..core.database import SessionLocal
from ..models import CheckIn, Recording
from .analysis import queue_window, apply_job_result, refresh_checkin
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
        queue_window(self.checkin_id, chunk)

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
        # writes `checkin.transcript`. Runs concurrently with analysis submissions
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
        with SessionLocal() as db:
            checkin = db.get(CheckIn, self.checkin_id)
            checkin.recording_completed_at = now()
            checkin.duration_seconds = self.bucketer.seconds
            db.commit()
        self.processing_complete = True
        await refresh_checkin(self.checkin_id, self)
        await self.emit("result", status="recording_saved")
        streams.remove(self.checkin_id)


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
