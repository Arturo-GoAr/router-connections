"""Conversión de modelos de base de datos a esquemas de respuesta."""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Device, DeviceSession, PortRecord, PortState, utcnow
from .schemas import DeviceDetail, DeviceRead, PortRead, SessionRead, TagRead


def open_session_of(session: Session, device: Device) -> DeviceSession | None:
    return session.exec(
        select(DeviceSession)
        .where(DeviceSession.device_id == device.id)
        .where(DeviceSession.ended_at.is_(None))
        .order_by(DeviceSession.started_at.desc())
    ).first()


def serialize_session(record: DeviceSession) -> SessionRead:
    end = record.ended_at or utcnow()
    return SessionRead(
        id=record.id,
        ip=record.ip,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_seconds=round((end - record.started_at).total_seconds(), 1),
    )


def serialize_port(record: PortRecord) -> PortRead:
    return PortRead(
        id=record.id,
        port=record.port,
        protocol=record.protocol,
        state=record.state.value,
        service=record.service,
        banner=record.banner,
        first_seen=record.first_seen,
        last_seen=record.last_seen,
    )


def serialize_device(session: Session, device: Device) -> DeviceRead:
    current = open_session_of(session, device)
    connected_since = current.started_at if current and device.is_online else None
    uptime = (
        round((utcnow() - connected_since).total_seconds(), 1)
        if connected_since
        else None
    )

    open_ports = session.exec(
        select(PortRecord)
        .where(PortRecord.device_id == device.id)
        .where(PortRecord.state == PortState.OPEN)
    ).all()

    return DeviceRead(
        id=device.id,
        mac=device.mac,
        ip=device.ip,
        display_name=device.display_name,
        hostname=device.hostname,
        friendly_name=device.friendly_name,
        alias=device.alias,
        vendor=device.vendor,
        model=device.model,
        category=device.category,
        detected_category=device.detected_category,
        category_override=device.category_override,
        detection_reason=device.detection_reason,
        detection_confidence=device.detection_confidence,
        notes=device.notes,
        is_favorite=device.is_favorite,
        is_gateway=device.is_gateway,
        is_self=device.is_self,
        is_online=device.is_online,
        first_seen=device.first_seen,
        last_seen=device.last_seen,
        last_port_scan=device.last_port_scan,
        connected_since=connected_since,
        uptime_seconds=uptime,
        open_port_count=len(open_ports),
        tags=[TagRead(id=tag.id, name=tag.name, color=tag.color) for tag in device.tags],
    )


def serialize_device_detail(
    session: Session, device: Device, session_limit: int = 20
) -> DeviceDetail:
    base = serialize_device(session, device)

    ports = session.exec(
        select(PortRecord)
        .where(PortRecord.device_id == device.id)
        .order_by(PortRecord.port)
    ).all()

    history = session.exec(
        select(DeviceSession)
        .where(DeviceSession.device_id == device.id)
        .order_by(DeviceSession.started_at.desc())
        .limit(session_limit)
    ).all()

    return DeviceDetail(
        **base.model_dump(),
        ports=[serialize_port(port) for port in ports],
        recent_sessions=[serialize_session(item) for item in history],
    )
