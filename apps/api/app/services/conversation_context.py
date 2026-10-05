"""Bounded, user-scoped history snapshots. No provider calls or audio reads."""
import json
from datetime import timedelta

from sqlalchemy import select

from ..models import AmplifierJob, AnalysisWindow, CheckIn, ConversationContext

MAX_CONVERSATIONS = 10
HISTORY_DAYS = 30
MAX_CONTEXT_CHARACTERS = 60_000
FORMAT_VERSION = 1
SIGNAL_FIELDS = (
    "name", "score", "level", "flagged", "latest_score", "baseline_score",
    "deviation_from_baseline", "anomaly", "z_score", "population_z",
)
QUALITY_FIELDS = ("issues", "voice_percentage", "audio_clarity")


def _timestamp(value):
    # Database timestamps are UTC without timezone, like CheckIn.started_at.
    return value.isoformat() + "Z" if value is not None else None


def _render(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fit(snapshot):
    """Prefer recent records; mark every excerpt/omission in the saved JSON."""
    rendered = _render(snapshot)
    # Excerpt older transcripts first. Binary search accounts for JSON escaping.
    for record in snapshot["conversations"]:
        if len(rendered) <= MAX_CONTEXT_CHARACTERS:
            break
        original = record["transcript"]
        if not original:
            continue
        record["transcript"] = ""
        record["transcript_omitted_characters"] = len(original)
        if len(_render(snapshot)) <= MAX_CONTEXT_CHARACTERS:
            low, high = 0, len(original)
            while low < high:
                middle = (low + high + 1) // 2
                record["transcript"] = original[:middle]
                record["transcript_omitted_characters"] = len(original) - middle
                if len(_render(snapshot)) <= MAX_CONTEXT_CHARACTERS:
                    low = middle
                else:
                    high = middle - 1
            record["transcript"] = original[:low]
            record["transcript_omitted_characters"] = len(original) - low
        rendered = _render(snapshot)
    # Preserve individual measurements; never average windows to save space.
    for record in snapshot["conversations"]:
        while len(rendered) > MAX_CONTEXT_CHARACTERS and record["analysis"]["windows"]:
            record["analysis"]["windows"].pop(0)
            record["analysis"]["omitted_windows"] += 1
            rendered = _render(snapshot)
    while len(rendered) > MAX_CONTEXT_CHARACTERS and snapshot["conversations"]:
        snapshot["conversations"].pop(0)
        snapshot["omitted_conversations"] += 1
        rendered = _render(snapshot)
    return rendered


def capture_conversation_context(db, checkin):
    """Add a snapshot in the caller's creation transaction; caller commits both."""
    captured_at = checkin.started_at
    sources = list(db.scalars(select(CheckIn).where(
        CheckIn.user_id == checkin.user_id,
        CheckIn.checkin_id != checkin.checkin_id,
        CheckIn.started_at >= captured_at - timedelta(days=HISTORY_DAYS),
        CheckIn.started_at < captured_at,
        CheckIn.recording_completed_at.is_not(None),
        CheckIn.recording_completed_at <= captured_at,
    ).order_by(CheckIn.started_at.desc(), CheckIn.checkin_id.desc()).limit(MAX_CONVERSATIONS)))
    sources.reverse()  # Chronological prompt order, most recent material last.
    source_ids = [source.checkin_id for source in sources]
    jobs_by_checkin = {source_id: [] for source_id in source_ids}
    windows_by_job = {}
    if source_ids:
        jobs = db.scalars(select(AmplifierJob).where(
            AmplifierJob.checkin_id.in_(source_ids),
            AmplifierJob.created_at <= captured_at,
            ~AmplifierJob.job_id.startswith("mock-"),
        ).order_by(AmplifierJob.recorded_at, AmplifierJob.created_at, AmplifierJob.job_id))
        for job in jobs:
            jobs_by_checkin[job.checkin_id].append(job)
        # Select metadata only: never load retained retry audio into history.
        windows = db.execute(select(
            AnalysisWindow.current_job_id, AnalysisWindow.window_id,
            AnalysisWindow.start_seconds, AnalysisWindow.end_seconds,
        ).where(AnalysisWindow.checkin_id.in_(source_ids)))
        windows_by_job = {window.current_job_id: window for window in windows}
    snapshot = {"format_version": FORMAT_VERSION, "captured_at": _timestamp(captured_at),
                "history_days": HISTORY_DAYS, "omitted_conversations": 0, "conversations": []}
    for source in sources:
        analysis = {"availability": "unavailable", "status_counts": {}, "omitted_windows": 0, "windows": []}
        for job in jobs_by_checkin[source.checkin_id]:
            # A callback committed after capture belongs to the next conversation.
            status = "pending" if job.completed_at and job.completed_at > captured_at else job.status
            analysis["status_counts"][status] = analysis["status_counts"].get(status, 0) + 1
            if status != "done":
                continue
            result = (job.raw_response or {}).get("result") or {}
            window = windows_by_job.get(job.job_id)
            analysis["windows"].append({
                "job_id": job.job_id, "recorded_at": _timestamp(job.recorded_at),
                "window_id": window.window_id if window else None,
                "start_seconds": window.start_seconds if window else None,
                "end_seconds": window.end_seconds if window else None,
                "signals": [{field: signal.get(field) for field in SIGNAL_FIELDS}
                            for signal in result.get("signals") or []],
                "audio_quality": {field: (result.get("audio_quality") or {}).get(field)
                                  for field in QUALITY_FIELDS},
            })
        if analysis["windows"]:
            analysis["availability"] = "available"
        snapshot["conversations"].append({
            "checkin_id": source.checkin_id, "started_at": _timestamp(source.started_at),
            "recording_completed_at": _timestamp(source.recording_completed_at),
            "duration_seconds": source.duration_seconds,
            "transcript": source.transcript,
            "transcript_status": "available" if source.transcript else "unavailable",
            "transcript_omitted_characters": 0, "analysis": analysis,
        })
    context = ConversationContext(
        checkin_id=checkin.checkin_id, captured_at=captured_at, format_version=FORMAT_VERSION,
        source_checkin_ids=source_ids, rendered_context=_fit(snapshot), snapshot=snapshot,
    )
    db.add(context)
    return context


def historical_context(db, checkin_id):
    context = db.get(ConversationContext, checkin_id)
    # Legacy conversations keep their original prompt; never backfill on reply.
    return context.rendered_context if context else None
