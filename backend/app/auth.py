import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None or not secrets.compare_digest(credentials.credentials, settings().app_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")
    return "mvp-user"


@dataclass
class Ticket:
    checkin_id: str
    user_id: str
    expires_at: float


class StreamTickets:
    def __init__(self):
        self._tickets: dict[str, Ticket] = {}

    def mint(self, checkin_id: str, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tickets[token] = Ticket(checkin_id, user_id, time.time() + settings().stream_ticket_ttl_seconds)
        return token

    def consume(self, token: str, checkin_id: str) -> str | None:
        item = self._tickets.get(token)
        if not item or item.checkin_id != checkin_id or item.expires_at < time.time():
            return None
        self._tickets.pop(token, None)
        return item.user_id


tickets = StreamTickets()


def mint_stream_ticket(checkin_id: str, user_id: str) -> str:
    return tickets.mint(checkin_id, user_id)


def consume_stream_ticket(token: str, checkin_id: str) -> str | None:
    return tickets.consume(token, checkin_id)


async def verify_webhook(request: Request) -> bytes:
    return await request.body()
