"""Gestión de reglas del Firewall de Windows.

Se usan los cmdlets `*-NetFirewallRule` en lugar de `netsh` a propósito: la
salida de `netsh` está traducida al idioma del sistema y parsearla es frágil,
mientras que los cmdlets devuelven JSON con nombres de propiedad en inglés
siempre.

Por seguridad, la app **solo borra reglas que ella misma creó**. Todas llevan el
grupo `RouterConnections`, y `delete_rule` se niega a tocar cualquier otra: una
herramienta de portafolio no tiene por qué poder desarmar el firewall del
sistema.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass

from ..scanner.shell import IS_WINDOWS, as_list, powershell_json

log = logging.getLogger(__name__)

#: Etiqueta que marca las reglas creadas por esta aplicación.
MANAGED_GROUP = "RouterConnections"

VALID_PROTOCOLS = {"TCP", "UDP"}
VALID_DIRECTIONS = {"Inbound", "Outbound"}
VALID_ACTIONS = {"Allow", "Block"}


class FirewallError(RuntimeError):
    """Fallo al consultar o modificar el firewall."""


@dataclass(slots=True)
class FirewallRule:
    name: str
    display_name: str
    direction: str
    action: str
    enabled: bool
    protocol: str | None = None
    local_ports: str | None = None
    profile: str | None = None
    description: str | None = None
    managed: bool = False


def is_admin() -> bool:
    """Crear o borrar reglas exige elevación; consultarlas no."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _quote(value: str) -> str:
    """Escapa una cadena para incrustarla en comillas simples de PowerShell."""
    return value.replace("'", "''")


def _validate_port_spec(ports: str) -> str:
    """Acepta `8080`, `80,443` o `8000-8100`; rechaza cualquier otra cosa.

    Esto no es cosmético: la especificación se interpola en un comando de
    PowerShell, así que restringirla a dígitos, comas y guiones es lo que impide
    que un valor de la API acabe ejecutando otra cosa.
    """
    cleaned = ports.replace(" ", "")
    if not cleaned:
        raise FirewallError("Debes indicar al menos un puerto")
    for chunk in cleaned.split(","):
        parts = chunk.split("-")
        if len(parts) > 2 or not all(part.isdigit() for part in parts):
            raise FirewallError(f"Especificación de puertos inválida: {ports!r}")
        for part in parts:
            if not 0 < int(part) <= 65535:
                raise FirewallError(f"Puerto fuera de rango: {part}")
    return cleaned


async def list_rules(only_managed: bool = True) -> list[FirewallRule]:
    """Lista reglas del firewall con su filtro de puertos.

    Listar *todas* las reglas de Windows tarda varios segundos, así que por
    defecto solo se devuelven las de esta app.
    """
    if not IS_WINDOWS:
        return []

    selector = (
        f"Get-NetFirewallRule -Group '{MANAGED_GROUP}' -ErrorAction SilentlyContinue"
        if only_managed
        else "Get-NetFirewallRule -ErrorAction SilentlyContinue "
        "| Where-Object { $_.Enabled -eq 'True' }"
    )
    script = (
        f"{selector} | ForEach-Object {{ "
        "  $f = $_ | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue; "
        "  [PSCustomObject]@{ "
        "    Name = $_.Name; DisplayName = $_.DisplayName; "
        "    Direction = [string]$_.Direction; Action = [string]$_.Action; "
        "    Enabled = [string]$_.Enabled; Profile = [string]$_.Profile; "
        "    Group = $_.Group; Description = $_.Description; "
        "    Protocol = [string]$f.Protocol; "
        "    LocalPort = ($f.LocalPort -join ',') "
        "  } } | ConvertTo-Json -Depth 3 -Compress"
    )

    rules: list[FirewallRule] = []
    for row in as_list(await powershell_json(script, timeout=60.0)):
        if not isinstance(row, dict):
            continue
        rules.append(
            FirewallRule(
                name=row.get("Name") or "",
                display_name=row.get("DisplayName") or "",
                direction=row.get("Direction") or "",
                action=row.get("Action") or "",
                enabled=str(row.get("Enabled")).lower() in {"true", "1"},
                protocol=row.get("Protocol") or None,
                local_ports=row.get("LocalPort") or None,
                profile=row.get("Profile") or None,
                description=row.get("Description") or None,
                managed=(row.get("Group") or "") == MANAGED_GROUP,
            )
        )
    return rules


async def create_rule(
    display_name: str,
    ports: str,
    protocol: str = "TCP",
    direction: str = "Inbound",
    action: str = "Allow",
    description: str = "",
) -> FirewallRule:
    """Crea una regla en el grupo gestionado por la app."""
    if not IS_WINDOWS:
        raise FirewallError("El firewall de Windows solo está disponible en Windows")
    if not is_admin():
        raise FirewallError(
            "Se requieren permisos de administrador para modificar el firewall. "
            "Reinicia la aplicación con 'Ejecutar como administrador'."
        )

    protocol = protocol.upper()
    direction = direction.capitalize()
    action = action.capitalize()
    if protocol not in VALID_PROTOCOLS:
        raise FirewallError(f"Protocolo no soportado: {protocol}")
    if direction not in VALID_DIRECTIONS:
        raise FirewallError(f"Dirección no soportada: {direction}")
    if action not in VALID_ACTIONS:
        raise FirewallError(f"Acción no soportada: {action}")
    port_spec = _validate_port_spec(ports)

    if not display_name.strip():
        raise FirewallError("La regla necesita un nombre")

    script = (
        "$ErrorActionPreference='Stop'; try { "
        f"New-NetFirewallRule -DisplayName '{_quote(display_name)}' "
        f"-Group '{MANAGED_GROUP}' -Direction {direction} -Action {action} "
        f"-Protocol {protocol} -LocalPort {port_spec} "
        f"-Description '{_quote(description)}' -Enabled True | Out-Null; "
        "ConvertTo-Json @{ ok = $true } -Compress "
        "} catch { ConvertTo-Json @{ ok = $false; error = $_.Exception.Message } -Compress }"
    )
    result = await powershell_json(script, timeout=45.0)
    if not isinstance(result, dict) or not result.get("ok"):
        message = (result or {}).get("error", "El comando no devolvió resultado")
        raise FirewallError(f"No se pudo crear la regla: {message}")

    log.info("Regla de firewall creada: %s (%s/%s)", display_name, protocol, port_spec)
    return FirewallRule(
        name=display_name,
        display_name=display_name,
        direction=direction,
        action=action,
        enabled=True,
        protocol=protocol,
        local_ports=port_spec,
        description=description,
        managed=True,
    )


async def delete_rule(display_name: str) -> None:
    """Borra una regla, siempre que la haya creado esta app."""
    if not IS_WINDOWS:
        raise FirewallError("El firewall de Windows solo está disponible en Windows")
    if not is_admin():
        raise FirewallError(
            "Se requieren permisos de administrador para modificar el firewall."
        )

    # El filtro por grupo es la salvaguarda: aunque llegue el nombre de una
    # regla del sistema, `Remove-NetFirewallRule` no la encontrará.
    script = (
        "$ErrorActionPreference='Stop'; try { "
        f"$r = Get-NetFirewallRule -Group '{MANAGED_GROUP}' -ErrorAction SilentlyContinue "
        f"| Where-Object {{ $_.DisplayName -eq '{_quote(display_name)}' }}; "
        "if (-not $r) { ConvertTo-Json @{ ok = $false; error = 'notfound' } -Compress } "
        "else { $r | Remove-NetFirewallRule; ConvertTo-Json @{ ok = $true } -Compress } "
        "} catch { ConvertTo-Json @{ ok = $false; error = $_.Exception.Message } -Compress }"
    )
    result = await powershell_json(script, timeout=45.0)
    if not isinstance(result, dict) or not result.get("ok"):
        error = (result or {}).get("error", "desconocido")
        if error == "notfound":
            raise FirewallError(
                f"No existe una regla llamada {display_name!r} creada por esta app. "
                "Por seguridad solo se pueden borrar las reglas que creó Router Connections."
            )
        raise FirewallError(f"No se pudo borrar la regla: {error}")

    log.info("Regla de firewall borrada: %s", display_name)
