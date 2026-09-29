from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.auth import consume_stream_ticket
from ..services.streaming import streams
from .checkins import require_owned_checkin

router = APIRouter(prefix="/v1/checkins", tags=["checkins"])


@router.websocket("/{checkin_id}/stream")
async def stream_checkin(websocket: WebSocket, checkin_id: str, ticket: str) -> None:
    user_id = consume_stream_ticket(ticket, checkin_id)
    if user_id is None:
        await websocket.close(code=4401, reason="Invalid or expired stream ticket")
        return
    if require_owned_checkin(checkin_id, user_id) is None:
        await websocket.close(code=4404, reason="Check-in not found")
        return
    await websocket.accept()
    session = streams.create(checkin_id, user_id, websocket)
    await session.emit("connected", sample_rate=16000, encoding="pcm_s16le", window_seconds=30)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                # Raw receive() doesn't raise WebSocketDisconnect itself -- only the
                # receive_text/receive_bytes/receive_json wrappers do that. Calling
                # receive() again after this message (the old behavior: falling through
                # to the `continue` below) raises an unhandled RuntimeError instead.
                break
            if message.get("bytes") is not None:
                await session.ingest(message["bytes"])
                continue
            if message.get("text") is None:
                continue
            try:
                action = json.loads(message["text"]).get("type")
            except json.JSONDecodeError:
                await session.emit("error", code="invalid_control", message="Control messages must be JSON.")
                continue
            if action == "checkin.start":
                await session.start()
            elif action == "checkin.pause":
                await session.pause()
            elif action == "checkin.resume":
                await session.resume()
            elif action == "checkin.end":
                await session.finalize()
                break
            else:
                await session.emit("error", code="unknown_control", message="Unknown check-in control frame.")
    except WebSocketDisconnect:
        pass
    finally:
        if session.finalized:
            streams.remove(checkin_id)
