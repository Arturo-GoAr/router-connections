"""Endpoints de redirección de puertos en el router (UPnP IGD)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..schemas import PortMappingCreate, PortMappingRead, UpnpStatus
from ..services import upnp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upnp", tags=["redirección de puertos"])

UPNP_UNAVAILABLE = (
    "Ningún router de la red respondió al descubrimiento UPnP. Lo más habitual "
    "es que UPnP esté desactivado en la configuración del router; actívalo desde "
    "su panel de administración si quieres gestionar redirecciones desde aquí."
)

#: El descubrimiento SSDP tarda segundos, así que se cachea el gateway hallado.
_cached_gateway: upnp.Gateway | None = None


async def _require_gateway() -> upnp.Gateway:
    global _cached_gateway
    if not settings.enable_upnp:
        raise HTTPException(status_code=503, detail="UPnP está desactivado en la configuración")

    if _cached_gateway is None:
        _cached_gateway = await upnp.discover_gateway()
    if _cached_gateway is None:
        raise HTTPException(status_code=503, detail=UPNP_UNAVAILABLE)
    return _cached_gateway


@router.get("/status", response_model=UpnpStatus)
async def upnp_status(refresh: bool = Query(default=False)) -> UpnpStatus:
    """Indica si hay un router controlable por UPnP y quién es."""
    global _cached_gateway
    if not settings.enable_upnp:
        return UpnpStatus(available=False, reason="UPnP está desactivado en la configuración")

    if refresh or _cached_gateway is None:
        _cached_gateway = await upnp.discover_gateway()

    if _cached_gateway is None:
        return UpnpStatus(available=False, reason=UPNP_UNAVAILABLE)

    external_ip: str | None = None
    try:
        external_ip = await upnp.get_external_ip(_cached_gateway)
    except upnp.UpnpError as exc:
        log.debug("El router no devolvió la IP externa: %s", exc)

    return UpnpStatus(
        available=True,
        router_name=_cached_gateway.friendly_name,
        router_model=_cached_gateway.model,
        manufacturer=_cached_gateway.manufacturer,
        external_ip=external_ip,
    )


@router.get("/mappings", response_model=list[PortMappingRead])
async def list_mappings() -> list[PortMappingRead]:
    gateway = await _require_gateway()
    try:
        mappings = await upnp.list_mappings(gateway)
    except upnp.UpnpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [
        PortMappingRead(
            external_port=m.external_port,
            internal_port=m.internal_port,
            internal_client=m.internal_client,
            protocol=m.protocol,
            description=m.description,
            enabled=m.enabled,
            lease_duration=m.lease_duration,
        )
        for m in mappings
    ]


@router.post("/mappings", response_model=PortMappingRead, status_code=201)
async def create_mapping(payload: PortMappingCreate) -> PortMappingRead:
    """Abre un puerto en el router redirigiéndolo a un equipo de la red."""
    gateway = await _require_gateway()
    try:
        await upnp.add_mapping(
            gateway,
            external_port=payload.external_port,
            internal_port=payload.internal_port,
            internal_client=payload.internal_client,
            protocol=payload.protocol,
            description=payload.description,
            lease_duration=payload.lease_duration,
        )
    except upnp.UpnpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PortMappingRead(
        external_port=payload.external_port,
        internal_port=payload.internal_port,
        internal_client=payload.internal_client,
        protocol=payload.protocol,
        description=payload.description,
        enabled=True,
        lease_duration=payload.lease_duration,
    )


@router.delete("/mappings/{protocol}/{external_port}", status_code=204, response_model=None)
async def delete_mapping(protocol: str, external_port: int) -> None:
    """Cierra un puerto previamente redirigido."""
    if protocol.upper() not in {"TCP", "UDP"}:
        raise HTTPException(status_code=400, detail="El protocolo debe ser TCP o UDP")

    gateway = await _require_gateway()
    try:
        await upnp.delete_mapping(gateway, external_port, protocol)
    except upnp.UpnpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
