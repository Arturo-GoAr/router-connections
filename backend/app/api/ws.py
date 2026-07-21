"""WebSocket que retransmite los eventos del escáner a la interfaz."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..events import bus
from ..scanner import orchestrator

log = logging.getLogger(__name__)

router = APIRouter()

#: Cada cuánto se manda un ping si no hay eventos, para detectar clientes muertos.
HEARTBEAT_SECONDS = 25.0


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = bus.subscribe()

    await websocket.send_json(
        {"type": "hello", "payload": {"is_scanning": orchestrator.is_scanning()}}
    )

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                # Sin eventos que mandar: un ping confirma que el cliente sigue
                # ahí y mantiene viva la conexión a través de proxies.
                await websocket.send_json({"type": "ping", "payload": None})
                continue
            await websocket.send_json(message)
    except WebSocketDisconnect:
        log.debug("Cliente WebSocket desconectado")
    except Exception as exc:  # pragma: no cover - defensivo
        log.debug("WebSocket cerrado por error: %s", exc)
    finally:
        bus.unsubscribe(queue)
