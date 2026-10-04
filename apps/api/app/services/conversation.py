"""Server-side Sonnet calls. No audio, credentials, or biomarker scores go to the client."""
import httpx

from ..core.config import settings


class ConversationError(Exception):
    """A safe, user-facing error; never includes credentials or provider response bodies."""


class SonnetClient:
    async def reply(self, messages: list[dict[str, str]]) -> dict:
        config = settings()
        if not config.anthropic_api_key:
            raise ConversationError("Sonnet is not configured. Set ANTHROPIC_API_KEY on the server.")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": config.anthropic_api_key, "anthropic-version": "2023-06-01"},
                    json={
                        "model": config.anthropic_model,
                        "max_tokens": 600,
                        # Anthropic moves the cache breakpoint forward as history grows.
                        # Expiry or a short prompt still works as an ordinary request.
                        "cache_control": {"type": "ephemeral", "ttl": "5m"},
                        "system": (
                            "You are a supportive conversational wellness coach conducting a voice check-in. "
                            "Respond directly to what the person said, in a few concise sentences, and ask "
                            "at most one useful follow-up question. Do not invent health measurements or "
                            "diagnose conditions. The conversation consists of transcribed speech."
                        ),
                        "messages": messages,
                    },
                )
            if response.status_code in {401, 403}:
                raise ConversationError("Sonnet authentication failed. Check the server's Anthropic API key.")
            if response.status_code in {402, 429}:
                raise ConversationError("Sonnet is unavailable because of an account or rate limit. Try again shortly.")
            if not response.is_success:
                raise ConversationError("Sonnet could not respond. Please try End Turn again.")
            payload = response.json()
            reply = "\n".join(block["text"] for block in payload.get("content", [])
                              if block.get("type") == "text" and block.get("text")).strip()
            if not reply:
                raise ConversationError("Sonnet returned no reply. Please try End Turn again.")
            return {"reply": reply, "model": payload.get("model", config.anthropic_model), "raw_response": payload}
        except httpx.TimeoutException as exc:
            raise ConversationError("Sonnet took too long to respond. Please try End Turn again.") from exc
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            raise ConversationError("Sonnet could not be reached. Please try End Turn again.") from exc


async def process_conversation_turn(stream, start_sample: int, end_sample: int) -> None:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from ..core.database import SessionLocal
    from ..models import ConversationTurn
    from .audio import pcm_to_wav
    from .transcribe import transcriber

    with SessionLocal() as db:
        turn = db.scalar(select(ConversationTurn).where(
            ConversationTurn.checkin_id == stream.checkin_id,
            ConversationTurn.end_sample == end_sample,
        ))
        if turn is None:
            turn = ConversationTurn(checkin_id=stream.checkin_id, start_sample=start_sample, end_sample=end_sample)
            db.add(turn)
        turn.status, turn.error = "processing", None
        db.commit()
        turn_id, transcript = turn.turn_id, turn.transcript
        earlier = list(db.scalars(select(ConversationTurn).where(
            ConversationTurn.checkin_id == stream.checkin_id,
            ConversationTurn.status == "done",
            ConversationTurn.end_sample <= start_sample,
        ).order_by(ConversationTurn.end_sample)))
        messages = []
        for previous in earlier:
            messages.extend([{"role": "user", "content": previous.transcript},
                             {"role": "assistant", "content": previous.reply}])
    await stream.emit("turn_processing", turn_id=turn_id)
    try:
        # Transcribe the completed turn, independently of the AMPLIFIER cadence.
        # A retry reuses its authoritative transcript instead of reinterpreting audio.
        if not transcript:
            audio = bytes(stream.bucketer.buffer[start_sample * 2:end_sample * 2])
            transcript = (await transcriber().transcribe(pcm_to_wav(audio, stream.bucketer.sample_rate))).strip()
        if not transcript:
            raise ConversationError("No speech was transcribed. Resume speaking, then try End Turn again.")
        with SessionLocal() as db:
            db.get(ConversationTurn, turn_id).transcript = transcript
            db.commit()
        await stream.emit("turn_transcript", turn_id=turn_id, text=transcript)
        messages.append({"role": "user", "content": transcript})
        response = await SonnetClient().reply(messages)
        with SessionLocal() as db:
            turn = db.get(ConversationTurn, turn_id)
            turn.status, turn.reply, turn.model = "done", response["reply"], response["model"]
            turn.raw_response = response["raw_response"]
            turn.completed_at = datetime.now(timezone.utc)
            db.commit()
        stream.turn_start_sample = end_sample
        await stream.emit("turn_result", turn_id=turn_id, transcript=transcript,
                          reply=response["reply"], model=response["model"],
                          usage=response["raw_response"].get("usage", {}))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ConversationError) else "This turn could not be processed. Please try End Turn again."
        with SessionLocal() as db:
            turn = db.get(ConversationTurn, turn_id)
            turn.status, turn.error = "failed", message
            db.commit()
        await stream.emit("error", code="conversation_failed", turn_id=turn_id, message=message)


async def save_final_speech(stream) -> None:
    """Persist only speech not covered by a successful End Turn, without calling Claude."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from ..core.database import SessionLocal
    from ..models import CheckIn, ConversationTurn
    from .audio import pcm_to_wav
    from .transcribe import transcriber

    start, end = stream.turn_start_sample, len(stream.bucketer.buffer) // 2
    if end <= start:
        return
    with SessionLocal() as db:
        turn = db.scalar(select(ConversationTurn).where(
            ConversationTurn.checkin_id == stream.checkin_id, ConversationTurn.end_sample == end))
        if turn is None:
            turn = ConversationTurn(checkin_id=stream.checkin_id, start_sample=start, end_sample=end)
            db.add(turn)
        transcript = turn.transcript if turn.start_sample == start else None
        # When no turns were sent, the full recording is exactly this final segment.
        if transcript is None and start == 0:
            transcript = db.get(CheckIn, stream.checkin_id).transcript
        turn.start_sample, turn.status, turn.error = start, "processing", None
        db.commit()
        turn_id = turn.turn_id
    error = None
    try:
        if transcript is None:
            transcript = await transcriber().transcribe(pcm_to_wav(
                bytes(stream.bucketer.buffer[start * 2:end * 2]), stream.bucketer.sample_rate))
        transcript = transcript.strip()
    except Exception:
        error = "The final speech could not be transcribed. Your recording is saved."
    with SessionLocal() as db:
        turn = db.get(ConversationTurn, turn_id)
        turn.transcript, turn.reply = transcript, None
        turn.status = "transcription_failed" if error else "saved"
        turn.error, turn.completed_at = error, datetime.now(timezone.utc)
        db.commit()


def conversation_messages(db, checkin) -> list[dict]:
    """One ordered display history; failed audio attempts superseded by a saved span are omitted."""
    from sqlalchemy import select
    from ..models import ConversationTurn, ConversationTextTurn

    messages = [{"id": f"{checkin.checkin_id}-opening", "role": "assistant",
                 "text": "How are you feeling today?", "status": "done"}]
    turns = list(db.scalars(select(ConversationTurn).where(
        ConversationTurn.checkin_id == checkin.checkin_id).order_by(ConversationTurn.end_sample)))
    authoritative = [turn for turn in turns if turn.status in {"done", "saved", "transcription_failed"}]
    for turn in turns:
        if turn not in authoritative and any(other.start_sample <= turn.start_sample and
                other.end_sample >= turn.end_sample for other in authoritative):
            continue
        if turn.transcript or turn.status == "transcription_failed":
            messages.append({"id": f"{turn.turn_id}-user", "role": "user", "text": turn.transcript or "",
                             "status": turn.status, "error": turn.error})
        if turn.status == "done" and turn.reply:
            messages.append({"id": f"{turn.turn_id}-assistant", "role": "assistant",
                             "text": turn.reply, "status": "done"})
    # Compatibility for recordings saved before per-turn persistence existed.
    if not turns and checkin.completed_at and checkin.transcript:
        messages.append({"id": f"{checkin.checkin_id}-transcript", "role": "user",
                         "text": checkin.transcript, "status": "saved"})
    text_turns = db.scalars(select(ConversationTextTurn).where(
        ConversationTextTurn.checkin_id == checkin.checkin_id).order_by(
            ConversationTextTurn.created_at, ConversationTextTurn.request_id))
    for turn in text_turns:
        messages.append({"id": f"{turn.request_id}-user", "request_id": turn.request_id,
                         "role": "user", "text": turn.text, "status": turn.status, "error": turn.error})
        if turn.status == "done" and turn.reply:
            messages.append({"id": f"{turn.request_id}-assistant", "role": "assistant",
                             "text": turn.reply, "status": "done"})
    return messages


# Single-process prototype: locks are released after each request and weakly held
# so completed conversations do not accumulate locks indefinitely.
import asyncio
from weakref import WeakValueDictionary

text_turn_locks: WeakValueDictionary = WeakValueDictionary()


def text_turn_lock(checkin_id: str) -> asyncio.Lock:
    lock = text_turn_locks.get(checkin_id)
    if lock is None:
        lock = asyncio.Lock()
        text_turn_locks[checkin_id] = lock
    return lock


async def reply_to_text(checkin_id: str, request_id: str, text: str) -> None:
    """Caller owns the per-check-in lock and has checked ownership/completion."""
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from sqlalchemy import select
    from ..core.database import SessionLocal
    from ..models import CheckIn, ConversationTextTurn

    with SessionLocal() as db:
        turn = db.get(ConversationTextTurn, request_id)
        if turn and (turn.checkin_id != checkin_id or turn.text != text):
            raise HTTPException(409, "This request ID was already used for another message.")
        if turn and turn.status == "done":
            return
        # Retry the outstanding message before accepting another, preserving order.
        outstanding = db.scalar(select(ConversationTextTurn).where(
            ConversationTextTurn.checkin_id == checkin_id,
            ConversationTextTurn.status != "done",
            ConversationTextTurn.request_id != request_id))
        if outstanding:
            raise HTTPException(409, "Retry the previous message before sending another.")
        history = conversation_messages(db, db.get(CheckIn, checkin_id))
        # The opening question is UI copy, never part of the established voice prefix.
        messages = [{"role": item["role"], "content": item["text"]} for item in history[1:]
                    if item["status"] in {"done", "saved"} and item["text"]]
        if turn is None:
            turn = ConversationTextTurn(request_id=request_id, checkin_id=checkin_id, text=text)
            db.add(turn)
        turn.status, turn.error = "processing", None
        db.commit()
    try:
        response = await SonnetClient().reply([*messages, {"role": "user", "content": text}])
        with SessionLocal() as db:
            turn = db.get(ConversationTextTurn, request_id)
            turn.reply, turn.model, turn.raw_response = response["reply"], response["model"], response["raw_response"]
            turn.status, turn.completed_at = "done", datetime.now(timezone.utc)
            db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        message = str(exc) if isinstance(exc, ConversationError) else "This message could not be processed. Please retry."
        with SessionLocal() as db:
            turn = db.get(ConversationTextTurn, request_id)
            turn.status, turn.error = "failed", message.replace("End Turn again", "again")
            db.commit()
        if isinstance(exc, asyncio.CancelledError):
            raise
