"""Endpoints de dispositivos: listado, detalle, edición, etiquetas y puertos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, or_, select

from ..db import get_session
from ..events import bus
from ..models import Device, DeviceCategory, DeviceSession, Tag
from ..scanner import orchestrator
from ..schemas import DeviceDetail, DeviceRead, DeviceUpdate, PortRead, SessionRead
from ..serializers import (
    serialize_device,
    serialize_device_detail,
    serialize_port,
    serialize_session,
)

router = APIRouter(prefix="/devices", tags=["dispositivos"])


def _get_device(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@router.get("", response_model=list[DeviceRead])
def list_devices(
    online: bool | None = None,
    category: DeviceCategory | None = None,
    favorite: bool | None = None,
    q: str | None = Query(default=None, description="Busca en nombre, IP, MAC y fabricante"),
    session: Session = Depends(get_session),
) -> list[DeviceRead]:
    statement = select(Device)

    if online is not None:
        statement = statement.where(Device.is_online == online)
    if favorite is not None:
        statement = statement.where(Device.is_favorite == favorite)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                col(Device.alias).ilike(pattern),
                col(Device.hostname).ilike(pattern),
                col(Device.friendly_name).ilike(pattern),
                col(Device.ip).ilike(pattern),
                col(Device.mac).ilike(pattern),
                col(Device.vendor).ilike(pattern),
            )
        )

    devices = session.exec(statement).all()

    # La categoría efectiva depende de `category_override`, que es una propiedad
    # de Python y no una columna, así que este filtro va en memoria.
    if category is not None:
        devices = [device for device in devices if device.category == category]

    devices.sort(
        key=lambda d: (
            not d.is_online,
            not d.is_gateway,
            tuple(int(part) for part in d.ip.split(".")) if d.ip else (999,),
        )
    )
    return [serialize_device(session, device) for device in devices]


@router.get("/categories")
def list_categories() -> list[dict]:
    """Categorías disponibles, para poblar el selector de la interfaz."""
    labels = {
        DeviceCategory.ROUTER: "Router",
        DeviceCategory.MODEM: "Módem",
        DeviceCategory.ACCESS_POINT: "Punto de acceso",
        DeviceCategory.PC: "PC",
        DeviceCategory.LAPTOP: "Portátil",
        DeviceCategory.PHONE: "Teléfono",
        DeviceCategory.TABLET: "Tablet",
        DeviceCategory.TV: "TV",
        DeviceCategory.CONSOLE: "Consola",
        DeviceCategory.PRINTER: "Impresora",
        DeviceCategory.CAMERA: "Cámara",
        DeviceCategory.SPEAKER: "Altavoz",
        DeviceCategory.NAS: "NAS",
        DeviceCategory.IOT: "IoT",
        DeviceCategory.UNKNOWN: "Desconocido",
    }
    return [{"value": key.value, "label": label} for key, label in labels.items()]


@router.get("/{device_id}", response_model=DeviceDetail)
def get_device(device_id: int, session: Session = Depends(get_session)) -> DeviceDetail:
    return serialize_device_detail(session, _get_device(session, device_id))


@router.patch("/{device_id}", response_model=DeviceDetail)
def update_device(
    device_id: int, payload: DeviceUpdate, session: Session = Depends(get_session)
) -> DeviceDetail:
    """Actualiza los campos que controla el usuario (alias, notas, categoría)."""
    device = _get_device(session, device_id)

    if payload.alias is not None:
        device.alias = payload.alias
    if payload.notes is not None:
        device.notes = payload.notes.strip() or None
    if payload.is_favorite is not None:
        device.is_favorite = payload.is_favorite

    # El borrado explícito tiene prioridad: permite volver a la categoría
    # detectada automáticamente sin tener que adivinar cuál era.
    if payload.clear_category_override:
        device.category_override = None
    elif payload.category_override is not None:
        device.category_override = payload.category_override

    session.add(device)
    session.commit()
    session.refresh(device)

    bus.publish("device:updated", {"device_id": device_id})
    return serialize_device_detail(session, device)


@router.delete("/{device_id}", status_code=204, response_model=None)
def delete_device(device_id: int, session: Session = Depends(get_session)) -> None:
    """Olvida un dispositivo y todo su historial.

    Si sigue en la red, el siguiente barrido volverá a descubrirlo (sin alias ni
    etiquetas): esto borra el registro, no expulsa a nadie.
    """
    device = _get_device(session, device_id)
    session.delete(device)
    session.commit()
    bus.publish("device:deleted", {"device_id": device_id})


@router.get("/{device_id}/sessions", response_model=list[SessionRead])
def device_sessions(
    device_id: int, limit: int = 50, session: Session = Depends(get_session)
) -> list[SessionRead]:
    _get_device(session, device_id)
    records = session.exec(
        select(DeviceSession)
        .where(DeviceSession.device_id == device_id)
        .order_by(DeviceSession.started_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [serialize_session(record) for record in records]


@router.post("/{device_id}/scan-ports", response_model=list[PortRead])
async def scan_ports(
    device_id: int,
    profile: str = Query(default="common", pattern="^(quick|common|full)$"),
    session: Session = Depends(get_session),
) -> list[PortRead]:
    """Escanea los puertos de un dispositivo concreto bajo demanda."""
    device = _get_device(session, device_id)
    if not device.ip:
        raise HTTPException(status_code=400, detail="El dispositivo no tiene IP conocida")

    try:
        await orchestrator.scan_device_ports(device_id, profile=profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session.expire_all()
    device = _get_device(session, device_id)
    return [serialize_port(port) for port in sorted(device.ports, key=lambda p: p.port)]


@router.post("/{device_id}/tags/{tag_id}", response_model=DeviceDetail)
def attach_tag(
    device_id: int, tag_id: int, session: Session = Depends(get_session)
) -> DeviceDetail:
    device = _get_device(session, device_id)
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")

    if tag not in device.tags:
        device.tags.append(tag)
        session.add(device)
        session.commit()
        session.refresh(device)

    return serialize_device_detail(session, device)


@router.delete("/{device_id}/tags/{tag_id}", response_model=DeviceDetail)
def detach_tag(
    device_id: int, tag_id: int, session: Session = Depends(get_session)
) -> DeviceDetail:
    device = _get_device(session, device_id)
    tag = session.get(Tag, tag_id)
    if tag and tag in device.tags:
        device.tags.remove(tag)
        session.add(device)
        session.commit()
        session.refresh(device)

    return serialize_device_detail(session, device)
