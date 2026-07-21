"""Endpoints del Firewall de Windows."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..scanner.shell import IS_WINDOWS
from ..schemas import FirewallRuleCreate, FirewallRuleRead, FirewallStatus
from ..services import firewall

router = APIRouter(prefix="/firewall", tags=["firewall"])


def _to_schema(rule: firewall.FirewallRule) -> FirewallRuleRead:
    return FirewallRuleRead(
        name=rule.name,
        display_name=rule.display_name,
        direction=rule.direction,
        action=rule.action,
        enabled=rule.enabled,
        protocol=rule.protocol,
        local_ports=rule.local_ports,
        profile=rule.profile,
        description=rule.description,
        managed=rule.managed,
    )


def _guard() -> None:
    if not settings.enable_windows_firewall:
        raise HTTPException(
            status_code=503, detail="La gestión del firewall está desactivada en la configuración"
        )
    if not IS_WINDOWS:
        raise HTTPException(
            status_code=503, detail="El Firewall de Windows solo está disponible en Windows"
        )


@router.get("/status", response_model=FirewallStatus)
async def firewall_status() -> FirewallStatus:
    if not settings.enable_windows_firewall:
        return FirewallStatus(
            available=False, is_admin=False, reason="Desactivado en la configuración"
        )
    if not IS_WINDOWS:
        return FirewallStatus(
            available=False, is_admin=False, reason="Solo disponible en Windows"
        )

    is_admin = firewall.is_admin()
    return FirewallStatus(
        available=True,
        is_admin=is_admin,
        reason=(
            None
            if is_admin
            else "Puedes consultar las reglas, pero crear o borrar requiere "
            "ejecutar la aplicación como administrador."
        ),
    )


@router.get("/rules", response_model=list[FirewallRuleRead])
async def list_rules(
    only_managed: bool = Query(
        default=True,
        description="Solo las reglas creadas por esta app. En False lista todas "
        "las reglas activas de Windows, lo que tarda varios segundos.",
    )
) -> list[FirewallRuleRead]:
    _guard()
    return [_to_schema(rule) for rule in await firewall.list_rules(only_managed)]


@router.post("/rules", response_model=FirewallRuleRead, status_code=201)
async def create_rule(payload: FirewallRuleCreate) -> FirewallRuleRead:
    """Abre (o bloquea) un puerto en el Firewall de Windows de este equipo."""
    _guard()
    try:
        rule = await firewall.create_rule(
            display_name=payload.display_name,
            ports=payload.ports,
            protocol=payload.protocol,
            direction=payload.direction,
            action=payload.action,
            description=payload.description,
        )
    except firewall.FirewallError as exc:
        status = 403 if not firewall.is_admin() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return _to_schema(rule)


@router.delete("/rules/{display_name}", status_code=204, response_model=None)
async def delete_rule(display_name: str) -> None:
    """Borra una regla creada por esta app. No toca reglas del sistema."""
    _guard()
    try:
        await firewall.delete_rule(display_name)
    except firewall.FirewallError as exc:
        status = 403 if not firewall.is_admin() else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
