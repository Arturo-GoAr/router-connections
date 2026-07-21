"""Bus de eventos en memoria para empujar cambios a los clientes WebSocket."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

#: Si un cliente no consume sus mensajes, se descartan los más viejos en vez de
#: bloquear al productor: el escaneo nunca debe frenarse por una UI lenta.
QUEUE_SIZE = 64


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, payload: Any = None) -> None:
        message = {"type": event_type, "payload": payload}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    log.debug("Cliente WebSocket saturado; se descarta un evento")

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()
