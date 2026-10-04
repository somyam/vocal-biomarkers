import asyncio
import io
import threading
import uuid
import wave
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AmplifierJob, CheckIn, CheckInSignal, Recording, User
from app.services import streaming
from app.services.amplifier import PulseClient, pulse_group_id


SIGNALS = [
    {"name": "stress", "score": 0.7, "level": "elevated", "flagged": True,
     "latest_score": 0.6, "baseline_score": 0.4, "deviation_from_baseline": 0.2,
     "anomaly": True, "z_score": 2.1, "population_z": 1.4},
    {"name": "energy", "score": 0.0, "level": "low", "flagged": False,
     "latest_score": None, "baseline_score": None, "deviation_from_baseline": None,
     "anomaly": None, "z_score": None, "population_z": None},
]


def result_for(job_id, status="done"):
    return {"job_id": job_id, "status": status, "result": {
        "signals": SIGNALS if status == "done" else [],
        "summary": {"recommended_action": "monitor"},
        "audio_quality": {"issues": []}, "extended_metrics": {"example": 42},
    }}


class Socket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


class FakePulse:
    s = SimpleNamespace(pulse_max_attempts=2)

    def __init__(self, outcomes=None, submit_error=False, gate=None):
        self.outcomes = outcomes or ["done"]
        self.submit_error = submit_error
        self.gate = gate
        self.calls = []
        self.responses = {}

    async def submit(self, group_id, wav_bytes, recorded_at):
        if self.submit_error:
            raise RuntimeError("upload unavailable")
        job_id = f"test-{uuid.uuid4()}"
        self.calls.append((group_id, wav_bytes, recorded_at, job_id))
        return {"job_id": job_id, "status": "queued", "group_id": group_id, "recorded_at": recorded_at}

    async def wait_for_result(self, job_id):
        if self.gate:
            await self.gate.wait()
        index = next(i for i, call in enumerate(self.calls) if call[3] == job_id)
        outcome = self.outcomes[min(index, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        result = result_for(job_id, outcome)
        self.responses[job_id] = result
        return result


@pytest.fixture
def stream():
    user_id = f"test-{uuid.uuid4()}"
    with SessionLocal() as db:
        db.add(User(user_id=user_id))
        db.commit()
        checkin = CheckIn(user_id=user_id, started_at=datetime(2026, 10, 4, 12))
        db.add(checkin)
        db.commit()
        session = streaming.streams.create(checkin.checkin_id, user_id, Socket())
    yield session
    streaming.streams.remove(session.checkin_id)


def rows(stream):
    with SessionLocal() as db:
        checkin = db.get(CheckIn, stream.checkin_id)
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == stream.checkin_id)))
        signals = list(db.scalars(select(CheckInSignal).where(CheckInSignal.checkin_id == stream.checkin_id)))
        recording = db.scalar(select(Recording).where(Recording.checkin_id == stream.checkin_id))
        return checkin, jobs, signals, recording


async def record_and_save(stream, seconds):
    await stream.start()
    await stream.ingest(b"\0\0" * (16000 * seconds))
    await stream.finalize()


def test_real_amplifier_credentials_are_disabled():
    assert not PulseClient().enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds,windows", [
    (10, []), (20, [(0, 15)]),
    (46, [(0, 15), (0, 30), (15, 45)]),
    (60, [(0, 15), (0, 30), (15, 45), (30, 60)]),
])
async def test_save_persists_every_window_and_signal(stream, monkeypatch, seconds, windows):
    pulse = FakePulse()
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    await record_and_save(stream, seconds)
    checkin, jobs, signals, recording = rows(stream)
    assert checkin.completed_at is not None
    assert checkin.transcribed_at is not None
    assert checkin.transcript == "[mock transcript]"
    assert checkin.duration_seconds == seconds
    assert len(recording.audio_wav) == 44 + seconds * 32000
    assert len(jobs) == len(windows)
    assert len(signals) == len(windows) * len(SIGNALS)
    assert {r["job_id"] for r in checkin.pulse_json["jobs"]} == set(pulse.responses)
    for job in jobs:
        assert job.raw_response == pulse.responses[job.job_id]
        assert job.status == "done" and job.completed_at is not None and job.errors is None
        assert job.group_id == pulse_group_id(stream.user_id)
    for signal in signals:
        expected = next(s for s in SIGNALS if s["name"] == signal.signal_name)
        assert signal.user_id == stream.user_id
        for key, value in expected.items():
            if key != "name":
                assert getattr(signal, key) == value
    for call, (start, end) in zip(pulse.calls, windows):
        group, audio, recorded_at, _ = call
        assert group == pulse_group_id(stream.user_id)
        assert recorded_at == (datetime(2026, 10, 4, 12) + timedelta(seconds=start)).isoformat() + "Z"
        with wave.open(io.BytesIO(audio)) as wav:
            assert wav.getnframes() == (end - start) * 16000
    trace = [e for e in stream.socket.events if e["type"] == "analyzing"]
    assert [(e["start_seconds"], e["end_seconds"]) for e in trace] == windows
    assert all(e["path"] == f"/v2/models/pulse/groups/{pulse_group_id(stream.user_id)}/analyze/longitudinal" for e in trace)
    assert sum(e["type"] == "result" for e in stream.socket.events) == 1
    await stream.finalize()
    assert len(pulse.calls) == len(windows)


@pytest.mark.asyncio
async def test_paused_audio_does_not_advance_windows(stream, monkeypatch):
    pulse = FakePulse()
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    await stream.start()
    await stream.ingest(b"\0\0" * 16000 * 10)
    await stream.pause()
    await stream.ingest(b"\0\0" * 16000 * 60)
    await stream.resume()
    await stream.ingest(b"\0\0" * 16000 * 5)
    await stream.finalize()
    assert rows(stream)[0].duration_seconds == 15
    assert len(pulse.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcomes,expected", [
    (["failed", "done"], ["failed", "done"]),
    (["timed-out", "done"], ["timed-out", "done"]),
    (["failed", "failed"], ["failed", "failed"]),
    ([RuntimeError("poll unavailable")], ["failed"]),
])
async def test_failed_attempts_cannot_block_completion(stream, monkeypatch, outcomes, expected):
    pulse = FakePulse(outcomes)
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    await record_and_save(stream, 15)
    checkin, jobs, signals, _ = rows(stream)
    assert checkin.completed_at is not None
    assert sorted(j.status for j in jobs) == sorted(expected)
    assert all(j.completed_at is not None for j in jobs)
    assert all(j.errors is not None for j in jobs if j.status != "done")
    assert len(signals) == expected.count("done") * len(SIGNALS)
    assert {j.job_id for j in jobs} == {call[3] for call in pulse.calls}
    if isinstance(outcomes[0], Exception):
        assert jobs[0].raw_response["status"] == "queued"


@pytest.mark.asyncio
async def test_upload_failure_is_persisted_with_subject_metadata(stream, monkeypatch):
    monkeypatch.setattr(streaming, "PulseClient", lambda: FakePulse(submit_error=True))
    await record_and_save(stream, 15)
    checkin, jobs, signals, _ = rows(stream)
    assert checkin.completed_at is not None
    assert len(jobs) == 1 and not signals
    assert jobs[0].status == "failed"
    assert jobs[0].group_id == pulse_group_id(stream.user_id)
    assert jobs[0].recorded_at == checkin.started_at


def add_job(stream, start=0):
    job_id = f"test-{uuid.uuid4()}"
    with SessionLocal() as db:
        db.add(AmplifierJob(job_id=job_id, checkin_id=stream.checkin_id,
            recorded_at=datetime(2026, 10, 4, 12) + timedelta(seconds=start)))
        db.commit()
    return job_id


@pytest.mark.asyncio
async def test_concurrent_poll_and_webhook_insert_signals_once(stream):
    job_id = add_job(stream)
    barrier = threading.Barrier(2)

    def deliver():
        barrier.wait(timeout=5)
        return asyncio.run(streaming.apply_job_result(job_id, result_for(job_id)))

    accepted = await asyncio.gather(asyncio.to_thread(deliver), asyncio.to_thread(deliver))
    assert sorted(accepted) == [False, True]
    assert len(rows(stream)[2]) == len(SIGNALS)
    assert not await streaming.apply_job_result(job_id, result_for(job_id))


@pytest.mark.asyncio
async def test_signal_write_failure_rolls_back_terminal_claim(stream):
    job_id = add_job(stream)
    invalid = result_for(job_id)
    invalid["result"]["signals"] = [SIGNALS[0], {"name": "bad", "score": "invalid"}]
    with pytest.raises(ValueError):
        await streaming.apply_job_result(job_id, invalid)
    _, jobs, signals, _ = rows(stream)
    assert jobs[0].completed_at is None and jobs[0].status == "queued"
    assert signals == []
    assert await streaming.apply_job_result(job_id, result_for(job_id))


@pytest.mark.asyncio
async def test_out_of_order_results_preserve_each_window(stream):
    first, second = add_job(stream, 0), add_job(stream, 15)
    assert not await streaming.apply_job_result(first, {"status": "processing"})
    assert await streaming.apply_job_result(second, result_for(second))
    assert await streaming.apply_job_result(first, result_for(first))
    checkin, jobs, signals, _ = rows(stream)
    assert checkin.completed_at is None
    assert len(signals) == 4
    assert {s.recorded_at for s in signals} == {j.recorded_at for j in jobs}
    await record_and_save(stream, 10)
    assert [j["job_id"] for j in rows(stream)[0].pulse_json["jobs"]] == [first, second]


@pytest.mark.asyncio
async def test_timeout_keeps_jobs_alive_until_persisted(stream, monkeypatch):
    gate = asyncio.Event()
    pulse = FakePulse(gate=gate)
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    monkeypatch.setattr(settings(), "finalize_timeout_seconds", 0.02)
    await record_and_save(stream, 15)
    assert rows(stream)[0].completed_at is None
    assert stream.checkin_id in streaming.streams.sessions
    assert any(e.get("code") == "processing_timeout" for e in stream.socket.events)
    gate.set()
    await asyncio.wait_for(stream.finalization_task, 2)
    assert rows(stream)[0].completed_at is not None
    assert len(rows(stream)[2]) == len(SIGNALS)
    assert stream.checkin_id not in streaming.streams.sessions


@pytest.mark.asyncio
async def test_windows_are_submitted_and_persisted_before_save(stream, monkeypatch):
    pulse = FakePulse()
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    await stream.start()
    for count in range(1, 4):
        await stream.ingest(b"\0\0" * 16000 * 15)
        await asyncio.gather(*stream.processing_tasks)
        checkin, jobs, signals, recording = rows(stream)
        assert len(jobs) == count and len(signals) == count * len(SIGNALS)
        assert checkin.completed_at is None and recording is None
    await stream.ingest(b"\0\0" * 16000)
    await stream.finalize()
    assert len(pulse.calls) == 3
    assert rows(stream)[0].duration_seconds == 46


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_action", ["resume", "save"])
async def test_pause_holds_queued_analysis_until_explicit_action(stream, monkeypatch, finish_action):
    pulse = FakePulse()
    monkeypatch.setattr(streaming, "PulseClient", lambda: pulse)
    await stream.start()
    await stream.ingest(b"\0\0" * 16000 * 15)
    await stream.pause()
    await asyncio.sleep(0.02)
    assert pulse.calls == []
    assert rows(stream)[1] == []
    if finish_action == "resume":
        await stream.resume()
        await asyncio.gather(*stream.processing_tasks)
        assert len(pulse.calls) == 1
    await stream.finalize()
    assert len(pulse.calls) == 1
    assert rows(stream)[0].completed_at is not None


@pytest.mark.asyncio
async def test_pause_cancels_partial_and_discards_late_transcript(stream, monkeypatch):
    started = asyncio.Event()
    calls = []

    async def transcribe(audio):
        calls.append(audio)
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Even a worker that returns after cancellation cannot publish old text.
            return "late transcript must be discarded"

    monkeypatch.setattr(streaming, "transcriber", lambda: SimpleNamespace(transcribe=transcribe))
    await stream.start()
    await stream.ingest(b"\0\0" * 16000)
    stream._queue_partial_transcript()
    await started.wait()
    await stream.pause()
    stream._queue_partial_transcript()
    await asyncio.sleep(0.02)
    assert len(calls) == 1
    assert not any(e["type"] == "transcript_partial" for e in stream.socket.events)
    assert not stream.transcribing_partial
    await stream.resume()
    async def fresh_transcript(audio):
        return "fresh transcript"
    monkeypatch.setattr(streaming, "transcriber", lambda: SimpleNamespace(transcribe=fresh_transcript))
    stream._queue_partial_transcript()
    await asyncio.gather(*stream.partial_tasks)
    assert any(e.get("text") == "fresh transcript" for e in stream.socket.events)
    await stream.finalize()
