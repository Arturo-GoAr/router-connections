"""Endpoints sobre el estado de la red y el lanzamiento de barridos."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from ..models import Device, ScanRun
from ..db import get_session
from ..schemas import (
    Diagnostic,
    HopRead,
    InterfaceRead,
    NetworkRead,
    ScanRequest,
    ScanResultRead,
    TopologyRead,
)
from ..scanner import netinfo, orchestrator
from ..services import firewall as firewall_service

router = APIRouter(tags=["red"])


def _build_diagnostics(profile: str | None, is_admin: bool) -> list[Diagnostic]:
    """Explica al usuario por qué la app puede estar viendo menos de lo esperado."""
    diagnostics: list[Diagnostic] = []

    if profile and profile.lower() == "public":
        diagnostics.append(
            Diagnostic(
                level="warning",
                title="Tu red está marcada como Pública en Windows",
                detail=(
                    "En el perfil Público, el Firewall de Windows bloquea el "
                    "descubrimiento de red, así que mDNS, SSDP y NetBIOS devuelven "
                    "pocos nombres. Cambia la red a Privada en Configuración → Red "
                    "e Internet para obtener nombres de dispositivo más precisos."
                ),
            )
        )

    if not is_admin:
        diagnostics.append(
            Diagnostic(
                level="info",
                title="Ejecutándose sin permisos de administrador",
                detail=(
                    "El escaneo funciona igual, pero crear o borrar reglas del "
                    "Firewall de Windows requiere abrir la aplicación como "
                    "administrador."
                ),
            )
        )

    return diagnostics


@router.get("/network", response_model=NetworkRead)
async def get_network(session: Session = Depends(get_session)) -> NetworkRead:
    """Resumen del estado de la red: IP, topología, contadores y avisos."""
    interface, public_ip, topology, profile = await asyncio.gather(
        netinfo.get_primary_interface(),
        netinfo.get_public_ip(),
        netinfo.detect_topology(),
        netinfo.get_network_profile(),
    )

    device_count = session.exec(select(func.count()).select_from(Device)).one()
    online_count = session.exec(
        select(func.count()).select_from(Device).where(Device.is_online == True)  # noqa: E712
    ).one()
    last_scan = session.exec(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
    ).first()

    is_admin = firewall_service.is_admin()

    return NetworkRead(
        interface=(
            InterfaceRead(
                name=interface.name,
                ip=interface.ip,
                prefix_length=interface.prefix_length,
                cidr=interface.cidr,
                mac=interface.mac,
                gateway=interface.gateway,
                dns_servers=interface.dns_servers,
            )
            if interface
            else None
        ),
        public_ip=public_ip,
        topology=TopologyRead(
            kind=topology.kind,
            private_hops=topology.private_hops,
            behind_cgnat=topology.behind_cgnat,
            summary=topology.summary,
            hops=[
                HopRead(
                    ttl=hop.ttl,
                    ip=hop.ip,
                    rtt_ms=hop.rtt_ms,
                    is_private=hop.is_private,
                    is_cgnat=hop.is_cgnat,
                )
                for hop in topology.hops
            ],
        ),
        network_profile=profile,
        is_admin=is_admin,
        is_scanning=orchestrator.is_scanning(),
        device_count=device_count,
        online_count=online_count,
        last_scan_at=last_scan.started_at if last_scan else None,
        diagnostics=_build_diagnostics(profile, is_admin),
    )


@router.post("/scan", response_model=ScanResultRead)
async def trigger_scan(request: ScanRequest | None = None) -> ScanResultRead:
    """Lanza un barrido y espera a que termine."""
    payload = request or ScanRequest()
    summary = await orchestrator.run_scan(
        with_ports=payload.scan_ports, port_profile=payload.port_profile
    )
    return ScanResultRead(
        devices_found=summary.devices_found,
        new_devices=summary.new_devices,
        went_offline=summary.went_offline,
        duration_seconds=summary.duration_seconds,
        errors=summary.errors,
    )


@router.get("/scan/status")
async def scan_status() -> dict:
    return {"is_scanning": orchestrator.is_scanning()}


@router.get("/scan/history")
async def scan_history(
    limit: int = 20, session: Session = Depends(get_session)
) -> list[ScanRun]:
    return session.exec(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(min(limit, 100))
    ).all()
