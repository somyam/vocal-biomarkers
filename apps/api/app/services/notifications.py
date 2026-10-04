"""Single-process, coalescing notifications. Subscribers always read a fresh DB snapshot."""
import asyncio
from collections import defaultdict
from contextlib import contextmanager


class NotificationHub:
    def __init__(self):
        self.subscribers = defaultdict(set)

    @contextmanager
    def subscribe(self, checkin_id):
        queue = asyncio.Queue(maxsize=1)
        self.subscribers[checkin_id].add(queue)
        try:
            yield queue
        finally:
            self.subscribers[checkin_id].discard(queue)
            if not self.subscribers[checkin_id]:
                del self.subscribers[checkin_id]

    def publish(self, checkin_id):
        # Coalesce notifications, not business events: a snapshot includes every
        # committed change. There is no unbounded per-browser event backlog.
        for queue in tuple(self.subscribers.get(checkin_id, ())):
            if not queue.full():
                queue.put_nowait(None)


notifications = NotificationHub()
