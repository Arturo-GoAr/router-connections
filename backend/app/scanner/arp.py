"""Barrido de la red local por ARP, sin privilegios de administrador.

El truco: enviar un datagrama UDP a un puerto muerto de cada IP de la subred.
No hace falta que nadie conteste al UDP — basta con que el sistema operativo
tenga que resolver la MAC antes de enviarlo, lo que dispara un ARP request. Los
hosts vivos responden a nivel de capa 2 y quedan en la tabla ARP, que después
leemos. Así evitamos los sockets raw de ICMP, que sí exigirían privilegios.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass

from ..config import settings
from .macaddr import is_multicast, normalize_mac
from .netinfo import Interface
from .shell import IS_WINDOWS, as_list, powershell_json, run

log = logging.getLogger(__name__)

#: Puerto "discard" (RFC 863). Casi nunca hay nada escuchando, y no importa:
#: solo queremos provocar la resolución ARP.
NUDGE_PORT = 9

#: Techo de seguridad: una /16 tiene 65534 hosts y no tiene sentido barrerla.
MAX_SWEEP_HOSTS = 4096


@dataclass(slots=True)
class ArpEntry:
    ip: str
    mac: str
    state: str = "unknown"


async def nudge_hosts(hosts: list[str], concurrency: int) -> None:
    """Envía un UDP a cada host para forzar la resolución ARP."""
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(concurrency)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    async def ping_one(ip: str) -> None:
        async with semaphore:
            try:
                await loop.sock_sendto(sock, b"\x00", (ip, NUDGE_PORT))
            except (OSError, NotImplementedError):
                # Host inalcanzable o backend sin sock_sendto: da igual, el
                # ARP request ya salió o el host simplemente no existe.
                pass

    try:
        await asyncio.gather(*(ping_one(ip) for ip in hosts))
    finally:
        sock.close()


_ARP_LINE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+(\S+)"
)


def parse_arp_output(output: str) -> list[ArpEntry]:
    """Parsea `arp -a`. Respaldo por si `Get-NetNeighbor` no está disponible."""
    entries: list[ArpEntry] = []
    for line in output.splitlines():
        match = _ARP_LINE.match(line)
        if not match:
            continue
        mac = normalize_mac(match.group(2))
        if not mac or is_multicast(mac):
            continue
        entries.append(ArpEntry(ip=match.group(1), mac=mac, state=match.group(3)))
    return entries


async def _windows_neighbors() -> list[ArpEntry]:
    script = (
        "Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue "
        "| Where-Object { $_.State -ne 'Unreachable' -and $_.State -ne 'Incomplete' } "
        "| ForEach-Object { [PSCustomObject]@{ "
        "  Ip = $_.IPAddress; Mac = $_.LinkLayerAddress; State = [string]$_.State "
        "} } | ConvertTo-Json -Depth 3 -Compress"
    )
    entries: list[ArpEntry] = []
    for row in as_list(await powershell_json(script)):
        if not isinstance(row, dict):
            continue
        mac = normalize_mac(row.get("Mac"))
        ip = row.get("Ip")
        if not mac or not ip or is_multicast(mac):
            continue
        entries.append(ArpEntry(ip=ip, mac=mac, state=str(row.get("State") or "")))
    return entries


async def read_arp_table() -> list[ArpEntry]:
    if IS_WINDOWS:
        entries = await _windows_neighbors()
        if entries:
            return entries
    return parse_arp_output(await run(["arp", "-a"], timeout=15.0))


def sweep_targets(interface: Interface) -> list[str]:
    """IPs a sondear: todos los hosts de la subred menos la nuestra."""
    network = interface.network
    if network.num_addresses - 2 > MAX_SWEEP_HOSTS:
        log.warning(
            "Subred %s demasiado grande (%d hosts); se limita a los primeros %d.",
            network,
            network.num_addresses - 2,
            MAX_SWEEP_HOSTS,
        )
    targets: list[str] = []
    for host in network.hosts():
        text = str(host)
        if text != interface.ip:
            targets.append(text)
        if len(targets) >= MAX_SWEEP_HOSTS:
            break
    return targets


async def sweep(interface: Interface) -> list[ArpEntry]:
    """Barrido completo: sondea la subred y devuelve los vecinos encontrados."""
    targets = sweep_targets(interface)
    log.info("Sondeando %d direcciones en %s", len(targets), interface.network)

    await nudge_hosts(targets, settings.sweep_concurrency)
    # Damos tiempo a que lleguen las respuestas ARP antes de leer la tabla.
    await asyncio.sleep(settings.sweep_settle_seconds)

    network = interface.network
    found: dict[str, ArpEntry] = {}
    for entry in await read_arp_table():
        try:
            address = ipaddress.ip_address(entry.ip)
        except ValueError:
            continue
        if address not in network or address.is_multicast:
            continue
        if entry.ip == str(network.broadcast_address):
            continue
        # Un mismo dispositivo puede tener varias IPs; nos quedamos con la
        # primera vista para no duplicarlo.
        found.setdefault(entry.mac, entry)

    log.info("Barrido terminado: %d dispositivos", len(found))
    return list(found.values())
