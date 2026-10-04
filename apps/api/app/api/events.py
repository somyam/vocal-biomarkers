"""Authenticated snapshots pushed over a socket independent of microphone capture."""
import anyio

from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from starlette.websockets import WebSocketDisconnect

from ..core.auth import StreamTickets, require_user
from ..services.notifications import notifications
from .checkins import checkin_payload, require_owned_checkin

router = APIRouter(prefix='/v1/checkins', tags=['events'])
event_tickets = StreamTickets()  # Separate namespace: audio tickets cannot subscribe.


@router.post('/{checkin_id}/events-ticket')
def events_ticket(checkin_id: str, user_id: str = Depends(require_user)):
    require_owned_checkin(checkin_id, user_id)
    ticket = event_tickets.mint(checkin_id, user_id)
    return {'events_path': f'/v1/checkins/{checkin_id}/events?ticket={ticket}'}


@router.websocket('/{checkin_id}/events')
async def events(websocket: WebSocket, checkin_id: str, ticket: str):
    user_id = event_tickets.consume(ticket, checkin_id)
    if user_id is None:
        await websocket.close(code=4401)
        return
    try:
        require_owned_checkin(checkin_id, user_id)
    except HTTPException:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    # Register before reading the snapshot. One writer sends complete snapshots,
    # so events during send queue a subsequent fresh snapshot, never stale deltas.
    with notifications.subscribe(checkin_id) as queue:
        async def send_snapshots():
            sequence = 0
            while True:
                checkin = require_owned_checkin(checkin_id, user_id)
                snapshot = checkin_payload(checkin)
                await websocket.send_json({'type': 'checkin.snapshot', 'sequence': sequence, 'checkin': jsonable_encoder(snapshot)})
                sequence += 1
                await queue.get()

        async def wait_disconnect():
            while True:
                if (await websocket.receive())['type'] == 'websocket.disconnect':
                    return

        async with anyio.create_task_group() as group:
            group.start_soon(send_snapshots)
            try:
                await wait_disconnect()
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                group.cancel_scope.cancel()
