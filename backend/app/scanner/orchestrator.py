"""Orquestación del barrido completo y persistencia de los resultados.

Un barrido encadena: interfaz → topología → ARP → descubrimiento de nombres →
(opcional) puertos → clasificación → base de datos. Al final se reconcilia el
estado: quién sigue conectado, quién desapareció y desde cuándo.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import Session, select

from ..config import settings
from ..db import session_scope
from ..events import bus
from ..models import (
    Device,
    DeviceCategory,
    DeviceSession,
    DeviceSignal,
    PortRecord,
    PortState,
    ScanRun,
    utcnow,
)
from . import arp, discovery, netinfo, oui, portscan
from .classify import Evidence, classify

log = logging.getLogger(__name__)

#: Un único barrido a la vez: dos barridos concurrentes se pisarían en SQLite y
#: duplicarían tráfico en la red sin aportar nada.
_scan_lock = asyncio.Lock()


@dataclass
class ScanSummary:
    devices_found: int = 0
    new_devices: int = 0
    went_offline: int = 0
    duration_seconds: float = 0.0
    topology: netinfo.Topology | None = None
    interface: netinfo.Interface | None = None
    errors: list[str] = field(default_factory=list)


def is_scanning() -> bool:
    return _scan_lock.locked()


def _upsert_device(
    session: Session,
    mac: str,
    ip: str,
    now,
) -> tuple[Device, bool]:
    """Busca el dispositivo por MAC o lo crea. Devuelve (device, es_nuevo)."""
    device = session.exec(select(Device).where(Device.mac == mac)).first()
    if device:
        device.ip = ip
        device.last_seen = now
        device.is_online = True
        return device, False

    device = Device(mac=mac, ip=ip, first_seen=now, last_seen=now, is_online=True)
    session.add(device)
    session.flush()  # necesitamos el id para las relaciones
    return device, True


def _touch_session(session: Session, device: Device, ip: str, now) -> None:
    """Mantiene abierta la sesión de conexión, o abre una nueva si no había.

    Esto es lo que responde "¿desde cuándo está conectado?": `started_at` de la
    sesión sin cerrar.
    """
    open_session = session.exec(
        select(DeviceSession)
        .where(DeviceSession.device_id == device.id)
        .where(DeviceSession.ended_at.is_(None))
        .order_by(DeviceSession.started_at.desc())
    ).first()

    if open_session:
        open_session.last_seen = now
        open_session.ip = ip
        return

    session.add(DeviceSession(device_id=device.id, ip=ip, started_at=now, last_seen=now))


def _close_stale_devices(session: Session, seen_macs: set[str], now) -> int:
    """Marca offline a quien lleva demasiado sin aparecer y cierra su sesión.

    Se usa un periodo de gracia porque un dispositivo puede faltar en un barrido
    puntual (wifi dormido, respuesta ARP perdida) sin haberse desconectado.
    """
    cutoff = now - timedelta(minutes=settings.offline_grace_minutes)
    stale = session.exec(
        select(Device).where(Device.is_online == True)  # noqa: E712
    ).all()

    closed = 0
    for device in stale:
        if device.mac in seen_macs or device.last_seen > cutoff:
            continue
        device.is_online = False
        open_session = session.exec(
            select(DeviceSession)
            .where(DeviceSession.device_id == device.id)
            .where(DeviceSession.ended_at.is_(None))
        ).first()
        if open_session:
            # Cerramos en el último momento en que se vio, no ahora: el
            # dispositivo se fue en algún punto del periodo de gracia.
            open_session.ended_at = open_session.last_seen
        closed += 1
    return closed


#: Tipos de señal que se acumulan, en el orden en que se leen de `DiscoveryInfo`.
SIGNAL_KINDS = ("upnp", "mdns", "banner")


def _store_signals(
    session: Session, device: Device, info: discovery.DiscoveryInfo, now
) -> None:
    """Guarda las señales vistas en este barrido, sin borrar las anteriores.

    Las señales son intermitentes (una TV apagada no contesta a SSDP), así que
    se acumulan en vez de reemplazarse. `last_seen` permite saber cuándo se
    observó cada una por última vez.
    """
    observed = [
        *((("upnp"), value) for value in info.upnp_device_types),
        *((("mdns"), value) for value in info.mdns_services),
        *((("banner"), value) for value in info.server_banners),
    ]
    if not observed:
        return

    existing = {
        (record.kind, record.value): record
        for record in session.exec(
            select(DeviceSignal).where(DeviceSignal.device_id == device.id)
        ).all()
    }

    for kind, value in observed:
        record = existing.get((kind, value))
        if record:
            record.last_seen = now
        else:
            session.add(
                DeviceSignal(
                    device_id=device.id,
                    kind=kind,
                    value=value,
                    first_seen=now,
                    last_seen=now,
                )
            )


def _load_signals(session: Session, device: Device) -> dict[str, list[str]]:
    """Devuelve todas las señales acumuladas del dispositivo, agrupadas por tipo."""
    grouped: dict[str, list[str]] = {kind: [] for kind in SIGNAL_KINDS}
    for record in session.exec(
        select(DeviceSignal).where(DeviceSignal.device_id == device.id)
    ).all():
        grouped.setdefault(record.kind, []).append(record.value)
    return grouped


def _store_ports(
    session: Session, device: Device, open_ports: list[portscan.OpenPort], now
) -> None:
    """Actualiza los puertos del dispositivo con el resultado del escaneo."""
    existing = {
        record.port: record
        for record in session.exec(
            select(PortRecord).where(PortRecord.device_id == device.id)
        ).all()
    }
    open_numbers = {p.port for p in open_ports}

    for found in open_ports:
        record = existing.get(found.port)
        if record:
            record.state = PortState.OPEN
            record.service = found.service or record.service
            record.banner = found.banner or record.banner
            record.last_seen = now
        else:
            session.add(
                PortRecord(
                    device_id=device.id,
                    port=found.port,
                    service=found.service,
                    banner=found.banner,
                    first_seen=now,
                    last_seen=now,
                )
            )

    # Los que antes estaban abiertos y ahora no responden se marcan cerrados,
    # pero se conservan como historial en vez de borrarlos.
    for port, record in existing.items():
        if port not in open_numbers and record.state == PortState.OPEN:
            record.state = PortState.CLOSED
            record.last_seen = now

    device.last_port_scan = now


async def run_scan(
    with_ports: bool | None = None, port_profile: str = "quick"
) -> ScanSummary:
    """Ejecuta un barrido completo y persiste el resultado."""
    if _scan_lock.locked():
        log.info("Ya hay un barrido en curso; se ignora la petición")
        return ScanSummary(errors=["Ya hay un barrido en curso"])

    async with _scan_lock:
        started = utcnow()
        summary = ScanSummary()
        bus.publish("scan:started", {"started_at": started.isoformat()})

        with session_scope() as session:
            run = ScanRun(kind="sweep", started_at=started)
            session.add(run)
            session.flush()
            run_id = run.id

        try:
            summary = await _do_scan(with_ports, port_profile, summary)
        except Exception as exc:  # el scheduler no debe morir por un fallo
            log.exception("El barrido falló")
            summary.errors.append(str(exc))

        finished = utcnow()
        summary.duration_seconds = round((finished - started).total_seconds(), 2)

        with session_scope() as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.finished_at = finished
                run.devices_found = summary.devices_found
                run.new_devices = summary.new_devices
                run.error = "; ".join(summary.errors) or None

        bus.publish(
            "scan:finished",
            {
                "devices_found": summary.devices_found,
                "new_devices": summary.new_devices,
                "went_offline": summary.went_offline,
                "duration_seconds": summary.duration_seconds,
                "errors": summary.errors,
            },
        )
        return summary


async def _do_scan(
    with_ports: bool | None, port_profile: str, summary: ScanSummary
) -> ScanSummary:
    interface = await netinfo.get_primary_interface()
    if not interface:
        summary.errors.append("No se encontró ninguna interfaz de red activa")
        return summary
    summary.interface = interface

    # Topología y barrido ARP no dependen entre sí: van en paralelo.
    topology, entries = await asyncio.gather(
        netinfo.detect_topology(), arp.sweep(interface)
    )
    summary.topology = topology
    bus.publish("scan:progress", {"stage": "arp", "found": len(entries)})

    # Este mismo equipo no aparece en su propia tabla ARP, pero es un
    # dispositivo más de la red y el usuario espera verlo.
    hosts: dict[str, str] = {entry.ip: entry.mac for entry in entries}
    if interface.mac:
        hosts[interface.ip] = interface.mac

    ips = list(hosts)
    discovered = await discovery.discover_all(ips)
    bus.publish("scan:progress", {"stage": "discovery", "found": len(ips)})

    ports_by_ip: dict[str, list[portscan.OpenPort]] = {}
    should_scan_ports = (
        settings.port_scan_on_sweep if with_ports is None else with_ports
    )
    if should_scan_ports:
        ports_by_ip = await portscan.scan_many(ips, profile=port_profile)
        bus.publish("scan:progress", {"stage": "ports", "found": len(ports_by_ip)})

    now = utcnow()
    seen_macs = set(hosts.values())

    with session_scope() as session:
        for ip, mac in hosts.items():
            device, is_new = _upsert_device(session, mac, ip, now)
            summary.devices_found += 1
            summary.new_devices += int(is_new)

            info = discovered.get(ip)
            open_ports = ports_by_ip.get(ip, [])

            device.is_gateway = ip == interface.gateway
            device.is_self = ip == interface.ip
            device.vendor = oui.lookup(mac) or device.vendor
            if info:
                device.hostname = info.hostname or device.hostname
                device.friendly_name = info.friendly_name or device.friendly_name
                device.model = info.model or device.model
                _store_signals(session, device, info, now)
                # Las señales recién añadidas tienen que ser visibles para la
                # consulta que hace `_load_signals` justo debajo.
                session.flush()

            if open_ports:
                _store_ports(session, device, open_ports, now)

            known_ports = [
                record.port
                for record in session.exec(
                    select(PortRecord)
                    .where(PortRecord.device_id == device.id)
                    .where(PortRecord.state == PortState.OPEN)
                ).all()
            ]

            hop_index = (
                topology.private_hops.index(ip)
                if ip in topology.private_hops
                else None
            )
            # Se clasifica con TODAS las señales acumuladas, no solo con las de
            # este barrido: si no, un dispositivo dormido perdería su categoría.
            signals = _load_signals(session, device)
            evidence = Evidence(
                mac=mac,
                vendor=device.vendor,
                hostname=device.hostname,
                friendly_name=device.friendly_name,
                manufacturer=info.manufacturer if info else None,
                model=device.model,
                upnp_device_types=signals["upnp"],
                mdns_services=signals["mdns"],
                server_banners=signals["banner"],
                open_ports=known_ports,
                is_gateway=device.is_gateway,
                is_self=device.is_self,
                topology_kind=topology.kind,
                hop_index=hop_index,
            )
            result = classify(evidence)
            device.detected_category = result.category
            device.detection_reason = result.reason_text
            device.detection_confidence = result.confidence

            _touch_session(session, device, ip, now)

        summary.went_offline = _close_stale_devices(session, seen_macs, now)

    bus.publish("devices:updated", {"count": summary.devices_found})
    return summary


async def scan_device_ports(device_id: int, profile: str = "common") -> list[dict]:
    """Escanea los puertos de un solo dispositivo y guarda el resultado."""
    with session_scope() as session:
        device = session.get(Device, device_id)
        if not device or not device.ip:
            raise ValueError("Dispositivo no encontrado o sin IP conocida")
        ip = device.ip

    bus.publish("ports:scanning", {"device_id": device_id, "ip": ip})
    open_ports = await portscan.scan_host(ip, profile=profile)
    now = utcnow()

    with session_scope() as session:
        device = session.get(Device, device_id)
        if device:
            _store_ports(session, device, open_ports, now)
            # Los puertos abiertos son una señal fuerte: reclasificamos, pero
            # sin perder lo que ya se sabía por SSDP y mDNS.
            signals = _load_signals(session, device)
            evidence = Evidence(
                mac=device.mac,
                vendor=device.vendor,
                hostname=device.hostname,
                friendly_name=device.friendly_name,
                model=device.model,
                upnp_device_types=signals["upnp"],
                mdns_services=signals["mdns"],
                server_banners=signals["banner"],
                open_ports=[p.port for p in open_ports],
                is_gateway=device.is_gateway,
                is_self=device.is_self,
            )
            if device.detected_category == DeviceCategory.UNKNOWN or open_ports:
                result = classify(evidence)
                if result.confidence >= device.detection_confidence:
                    device.detected_category = result.category
                    device.detection_reason = result.reason_text
                    device.detection_confidence = result.confidence

    payload = [
        {"port": p.port, "service": p.service, "banner": p.banner} for p in open_ports
    ]
    bus.publish("ports:scanned", {"device_id": device_id, "open_ports": payload})
    return payload
