"""Webhook-driven analysis. No background job-status requests."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..core.config import settings
from ..core.database import SessionLocal
from ..models import AnalysisWindow, AmplifierJob, CheckIn, CheckInSignal, WebhookInbox
from .amplifier import PulseClient, TERMINAL, pulse_group_id
from .notifications import notifications

log = logging.getLogger(__name__)
submission_tasks: dict[str, asyncio.Task] = {}
deadlines: dict[str, asyncio.TimerHandle] = {}


def now():
    return datetime.now(timezone.utc)


def age_seconds(value):
    return (now() - value.replace(tzinfo=timezone.utc)).total_seconds()


def analysis_status(db, checkin_id):
    windows = list(db.scalars(select(AnalysisWindow).where(AnalysisWindow.checkin_id == checkin_id)))
    jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)))
    pending = [row for row in [*windows, *jobs] if row.status not in TERMINAL]
    if pending:
        return 'delayed' if any(age_seconds(row.created_at) >= settings().analysis_delay_seconds for row in pending) else 'pending'
    outcomes = windows or jobs
    return 'failed' if any(row.status != 'done' for row in outcomes) else 'complete'


def schedule_deadline(key, checkin_id, created_at):
    if key in deadlines:
        return
    def delayed():
        deadlines.pop(key, None)
        notifications.publish(checkin_id)
    seconds = max(0, settings().analysis_delay_seconds - age_seconds(created_at))
    deadlines[key] = asyncio.get_running_loop().call_later(seconds, delayed)


def cancel_deadline(key):
    handle = deadlines.pop(key, None)
    if handle:
        handle.cancel()


def queue_window(checkin_id, chunk):
    with SessionLocal() as db:
        window = AnalysisWindow(checkin_id=checkin_id, index=chunk.index,
            start_seconds=chunk.start_seconds, end_seconds=chunk.end_seconds,
            audio_wav=chunk.wav_bytes, max_attempts=max(1, settings().pulse_max_attempts))
        db.add(window)
        db.commit()
        window_id, created_at = window.window_id, window.created_at
    notifications.publish(checkin_id)
    schedule_deadline('window:' + window_id, checkin_id, created_at)
    schedule_submission(window_id)
    return window_id


def schedule_submission(window_id):
    existing = submission_tasks.get(window_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(submit_window(window_id))
    submission_tasks[window_id] = task
    def finished(done):
        if submission_tasks.get(window_id) is done:
            submission_tasks.pop(window_id, None)
        if not done.cancelled() and done.exception():
            error = done.exception()
            log.error('Analysis submission task failed', exc_info=(type(error), error, error.__traceback__))
        # A very fast callback can queue a retry while this attempt is still
        # returning. Recheck exactly once on task completion, never on a timer.
        if not done.cancelled():
            with SessionLocal() as db:
                row = db.get(AnalysisWindow, window_id)
                retry = row is not None and row.status == 'queued'
            if retry:
                schedule_submission(window_id)
    task.add_done_callback(finished)


def live_stream(checkin_id):
    from .streaming import streams
    return streams.sessions.get(checkin_id)


async def submit_window(window_id):
    with SessionLocal() as db:
        window = db.get(AnalysisWindow, window_id)
        if window is None or window.status != 'queued':
            return
        checkin_id = window.checkin_id
    stream = live_stream(checkin_id)
    if stream:
        await stream.wait_until_active()
    with SessionLocal() as db:
        window = db.get(AnalysisWindow, window_id)
        if window.status != 'queued':
            return
        checkin = db.get(CheckIn, checkin_id)
        user_id = checkin.user_id
        captured = checkin.started_at + timedelta(seconds=window.start_seconds)
        recorded_at = captured.replace(tzinfo=timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        audio = window.audio_wav
        index, start, end = window.index, window.start_seconds, window.end_seconds
        window.status, window.attempts = 'submitting', window.attempts + 1
        db.commit()
    client = PulseClient()
    if stream:
        client.wait_until_active = stream.wait_until_active
    try:
        submission = await client.submit(pulse_group_id(user_id), audio, recorded_at)
        job_id = str(submission.get('job_id') or submission.get('id') or '')
        if not job_id:
            raise ValueError('Analysis provider did not return a job ID.')
        with SessionLocal() as db:
            # Terminal submissions use the same atomic result path as callbacks.
            job = AmplifierJob(job_id=job_id, checkin_id=checkin_id, group_id=pulse_group_id(user_id),
                               recorded_at=captured, status='queued', raw_response=submission)
            db.add(job)
            window = db.get(AnalysisWindow, window_id)
            window.current_job_id, window.status = job_id, 'waiting'
            db.commit()
            created_at = job.created_at
        schedule_deadline('job:' + job_id, checkin_id, created_at)
        if stream:
            await stream.emit('analyzing', chunk=index, job_id=job_id, method='POST',
                path=f'/v2/models/pulse/groups/{pulse_group_id(user_id)}/analyze/longitudinal',
                start_seconds=start, end_seconds=end)
        if str(submission.get('status', '')).lower() in TERMINAL:
            await receive_result(job_id, submission)
        else:
            await reconcile_inbox(job_id)
        await refresh_checkin(checkin_id)
    except asyncio.CancelledError:
        # Accepted jobs survive in Postgres. Recovery treats an interrupted
        # submission with no known provider ID as uncertain, not safe to resubmit.
        raise
    except Exception:
        log.exception('Unable to submit analysis window %s', window_id)
        with SessionLocal() as db:
            window = db.get(AnalysisWindow, window_id)
            # Never convert an accepted job to failed just because notification
            # delivery or local processing failed. Its callback can still arrive.
            if window.status == 'submitting':
                window.status, window.audio_wav = 'failed', None
                db.add(AmplifierJob(job_id=f'local-failure-{uuid.uuid4()}', checkin_id=checkin_id,
                    group_id=pulse_group_id(user_id), recorded_at=captured, status='failed',
                    errors={'message': 'Analysis submission failed. Check server configuration or provider availability.'},
                    completed_at=now()))
                db.commit()
                cancel_deadline('window:' + window_id)
        if stream:
            await stream.emit('error', code='pulse_processing_failed', message='We could not submit this audio for analysis.')
        await refresh_checkin(checkin_id)


async def receive_result(job_id, result):
    """Durably acknowledge the first terminal callback, even before job registration."""
    if str(result.get('status', '')).lower() not in TERMINAL:
        return False
    with SessionLocal() as db:
        try:
            db.add(WebhookInbox(job_id=job_id, payload=result))
            db.commit()
        except IntegrityError:
            db.rollback()  # Duplicate delivery; replay the original durable payload.
    return await reconcile_inbox(job_id)


async def reconcile_inbox(job_id):
    with SessionLocal() as db:
        inbox = db.get(WebhookInbox, job_id)
        if inbox is None or inbox.applied_at is not None:
            return False
        payload = inbox.payload
    return await apply_job_result(job_id, payload)


async def apply_job_result(job_id, result, stream=None):
    status = str(result.get('status', '')).lower()
    if status not in TERMINAL:
        return False
    retry_id = None
    finished_window = None
    trace = None
    with SessionLocal() as db:
        claimed = db.execute(update(AmplifierJob).where(
            AmplifierJob.job_id == job_id, AmplifierJob.completed_at.is_(None)
        ).values(status=status, raw_response=result, errors=None if status == 'done' else result,
                 completed_at=now()).returning(AmplifierJob.checkin_id, AmplifierJob.recorded_at)).first()
        if claimed is None:
            # Unknown job remains in the inbox for submission registration/startup.
            job = db.get(AmplifierJob, job_id)
            if job and job.completed_at:
                inbox = db.get(WebhookInbox, job_id)
                if inbox:
                    inbox.applied_at = now()
                    db.commit()
            return False
        checkin_id, recorded_at = claimed
        checkin = db.get(CheckIn, checkin_id)
        if status == 'done':
            for signal in (result.get('result') or {}).get('signals') or []:
                db.add(CheckInSignal(checkin_id=checkin_id, user_id=checkin.user_id,
                    signal_name=str(signal.get('name', '')), recorded_at=recorded_at or now(),
                    score=float(signal.get('score') or 0), level=str(signal.get('level', '')),
                    flagged=bool(signal.get('flagged', False)),
                    **{key: signal.get(key) for key in ('latest_score', 'baseline_score',
                       'deviation_from_baseline', 'anomaly', 'z_score', 'population_z')}))
        window = db.scalar(select(AnalysisWindow).where(AnalysisWindow.current_job_id == job_id))
        if window:
            trace = dict(chunk=window.index, start_seconds=window.start_seconds, end_seconds=window.end_seconds)
            if status != 'done' and window.attempts < window.max_attempts:
                window.status = 'queued'  # Same transaction as terminal job prevents false completion.
                retry_id = window.window_id
            else:
                window.status, window.audio_wav = ('done' if status == 'done' else 'failed'), None
                finished_window = window.window_id
        inbox = db.get(WebhookInbox, job_id)
        if inbox:
            inbox.applied_at = now()
        db.commit()
    cancel_deadline('job:' + job_id)
    if finished_window:
        cancel_deadline('window:' + finished_window)
    if retry_id:
        schedule_submission(retry_id)
    stream = stream or live_stream(checkin_id)
    if stream and trace:
        if status == 'done':
            await stream.emit('job_result', job_id=job_id, **trace,
                signals=[{'name': s.get('name'), 'level': s.get('level')} for s in (result.get('result') or {}).get('signals') or []])
        elif not retry_id:
            await stream.emit('error', code='pulse_processing_failed', message='We could not analyze this audio.')
    await refresh_checkin(checkin_id)
    return True


async def refresh_checkin(checkin_id, stream=None):
    with SessionLocal() as db:
        checkin = db.get(CheckIn, checkin_id)
        if checkin is None:
            return
        jobs = list(db.scalars(select(AmplifierJob).where(AmplifierJob.checkin_id == checkin_id)
                              .order_by(AmplifierJob.recorded_at, AmplifierJob.created_at, AmplifierJob.job_id)))
        checkin.pulse_json = {'jobs': [job.raw_response for job in jobs]}
        if checkin.recording_completed_at and analysis_status(db, checkin_id) in {'complete', 'failed'}:
            checkin.completed_at = checkin.completed_at or now()
        db.commit()
    notifications.publish(checkin_id)


async def recover_analysis():
    """One startup pass, then callbacks/deadlines. No provider queries."""
    with SessionLocal() as db:
        inbox_ids = list(db.scalars(select(WebhookInbox.job_id).where(WebhookInbox.applied_at.is_(None))))
    for job_id in inbox_ids:
        await reconcile_inbox(job_id)
    with SessionLocal() as db:
        windows = list(db.scalars(select(AnalysisWindow).where(AnalysisWindow.status.not_in(TERMINAL))))
        checkin_ids = set()
        for window in windows:
            checkin_ids.add(window.checkin_id)
            if window.status == 'submitting':
                window.status, window.audio_wav = 'failed', None
                db.add(AmplifierJob(job_id=f'local-failure-{uuid.uuid4()}', checkin_id=window.checkin_id,
                    status='failed', completed_at=now(), errors={'message': 'Submission interrupted; provider acceptance is unknown.'}))
            elif window.status == 'queued':
                schedule_deadline('window:' + window.window_id, window.checkin_id, window.created_at)
                schedule_submission(window.window_id)
            else:
                schedule_deadline('window:' + window.window_id, window.checkin_id, window.created_at)
        db.commit()
        for job in db.scalars(select(AmplifierJob).where(AmplifierJob.completed_at.is_(None))):
            checkin_ids.add(job.checkin_id)
            schedule_deadline('job:' + job.job_id, job.checkin_id, job.created_at)
        checkin_ids.update(db.scalars(select(CheckIn.checkin_id).where(
            CheckIn.recording_completed_at.is_not(None), CheckIn.completed_at.is_(None))))
    for checkin_id in checkin_ids:
        await refresh_checkin(checkin_id)


async def stop_analysis():
    for handle in deadlines.values():
        handle.cancel()
    deadlines.clear()
    tasks = list(submission_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    submission_tasks.clear()
