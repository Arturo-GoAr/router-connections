"""Routers de la API REST y el WebSocket."""

from fastapi import APIRouter

from . import devices, firewall, network, portforward, tags, ws

api_router = APIRouter(prefix="/api")
api_router.include_router(network.router)
api_router.include_router(devices.router)
api_router.include_router(tags.router)
api_router.include_router(portforward.router)
api_router.include_router(firewall.router)

__all__ = ["api_router", "ws"]
