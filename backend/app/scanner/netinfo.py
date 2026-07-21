"""Información de la red local: interfaces, gateway, IP pública y topología.

La parte interesante es `detect_topology`: mirando los primeros saltos de un
traceroute se puede saber si este equipo cuelga directamente del router
principal o si hay un segundo router haciendo NAT por encima (doble NAT), y si
el operador aplica CGNAT.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field

import httpx

from ..config import settings
from .shell import IS_WINDOWS, as_list, powershell_json, run

log = logging.getLogger(__name__)

#: Rango reservado para Carrier-Grade NAT (RFC 6598). Si aparece justo después
#: del gateway, el operador te está dando una IP compartida, no una pública.
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


@dataclass(slots=True)
class Interface:
    name: str
    ip: str
    prefix_length: int
    mac: str | None = None
    gateway: str | None = None
    dhcp_server: str | None = None
    dns_servers: list[str] = field(default_factory=list)

    @property
    def cidr(self) -> str:
        return f"{self.ip}/{self.prefix_length}"

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(self.cidr, strict=False)

    @property
    def host_count(self) -> int:
        return max(self.network.num_addresses - 2, 0)


@dataclass(slots=True)
class Hop:
    ttl: int
    ip: str | None
    rtt_ms: float | None = None

    @property
    def is_private(self) -> bool:
        if not self.ip:
            return False
        try:
            return ipaddress.ip_address(self.ip).is_private
        except ValueError:
            return False

    @property
    def is_cgnat(self) -> bool:
        if not self.ip:
            return False
        try:
            return ipaddress.ip_address(self.ip) in CGNAT_NETWORK
        except ValueError:
            return False


@dataclass(slots=True)
class Topology:
    """Resultado del análisis de saltos."""

    #: "direct" = un solo salto privado; "cascade" = doble NAT; "unknown".
    kind: str
    #: Saltos con IP privada, en orden (el primero es tu gateway).
    private_hops: list[str]
    behind_cgnat: bool
    hops: list[Hop]
    summary: str


def _is_virtual(name: str) -> bool:
    """Descarta adaptadores que no corresponden a una red física real."""
    lowered = name.lower()
    noise = ("bluetooth", "loopback", "vethernet", "vmware", "virtualbox", "hyper-v")
    return any(token in lowered for token in noise)


async def _windows_interfaces() -> list[Interface]:
    script = (
        "Get-NetIPConfiguration -Detailed "
        "| Where-Object { $_.IPv4Address -ne $null } "
        "| ForEach-Object { [PSCustomObject]@{ "
        "  Name = $_.InterfaceAlias; "
        "  Ip = $_.IPv4Address.IPAddress; "
        "  Prefix = $_.IPv4Address.PrefixLength; "
        "  Mac = $_.NetAdapter.MacAddress; "
        "  Gateway = ($_.IPv4DefaultGateway | Select-Object -First 1).NextHop; "
        "  Dns = @($_.DNSServer | Where-Object {$_.AddressFamily -eq 2} "
        "         | ForEach-Object { $_.ServerAddresses }) "
        "} } | ConvertTo-Json -Depth 4 -Compress"
    )
    interfaces: list[Interface] = []
    for row in as_list(await powershell_json(script)):
        if not isinstance(row, dict) or not row.get("Ip"):
            continue
        name = row.get("Name") or "?"
        if _is_virtual(name):
            continue
        mac = row.get("Mac")
        interfaces.append(
            Interface(
                name=name,
                ip=row["Ip"],
                prefix_length=int(row.get("Prefix") or 24),
                mac=mac.replace("-", ":").lower() if mac else None,
                gateway=row.get("Gateway"),
                dns_servers=[d for d in as_list(row.get("Dns")) if isinstance(d, str)],
            )
        )
    return interfaces


def _fallback_interface() -> list[Interface]:
    """Último recurso multiplataforma: la IP con la que salimos a internet.

    El socket UDP no envía nada, solo obliga al SO a elegir una ruta.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except OSError:
        return []
    finally:
        sock.close()
    return [Interface(name="default", ip=ip, prefix_length=24)]


async def get_interfaces() -> list[Interface]:
    interfaces: list[Interface] = []
    if IS_WINDOWS:
        interfaces = await _windows_interfaces()
    if not interfaces:
        interfaces = _fallback_interface()
    return interfaces


async def get_primary_interface() -> Interface | None:
    """La interfaz por la que sale el tráfico: la que tiene default gateway."""
    interfaces = await get_interfaces()
    if not interfaces:
        return None
    with_gateway = [i for i in interfaces if i.gateway]
    if with_gateway:
        return with_gateway[0]
    # Sin gateway conocido preferimos una IP privada antes que una APIPA.
    for iface in interfaces:
        if not iface.ip.startswith("169.254."):
            return iface
    return interfaces[0]


async def get_public_ip() -> str | None:
    """Consulta la IP pública a un servicio externo (desactivable por config)."""
    if not settings.enable_public_ip_lookup:
        return None
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(settings.public_ip_service)
            response.raise_for_status()
            candidate = response.text.strip()
        ipaddress.ip_address(candidate)
        return candidate
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("No se pudo obtener la IP pública: %s", exc)
        return None


async def get_network_profile() -> str | None:
    """Categoría de red de Windows: Public, Private o DomainAuthenticated.

    Importa más de lo que parece: en el perfil `Public` el Firewall de Windows
    bloquea el descubrimiento de red, así que mDNS, SSDP y NetBIOS devuelven
    poco o nada. La UI lo avisa en vez de dejar al usuario pensando que la app
    está rota.
    """
    if not IS_WINDOWS:
        return None
    # El cast a [string] es imprescindible: `NetworkCategory` es un enum y
    # `ConvertTo-Json` lo serializaría como su valor numérico (Public = 0).
    script = (
        "[string]((Get-NetConnectionProfile | Select-Object -First 1).NetworkCategory) "
        "| ConvertTo-Json -Compress"
    )
    value = await powershell_json(script)
    return value if isinstance(value, str) and value else None


_HOP_IP = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
_HOP_RTT = re.compile(r"(\d+)\s*ms")


def parse_traceroute(output: str, max_hops: int) -> list[Hop]:
    """Parsea la salida de `tracert`/`traceroute` de forma tolerante al idioma.

    Solo nos apoyamos en la forma de las líneas (número de salto + IP), nunca en
    los textos, que cambian con el idioma de Windows.
    """
    hops: list[Hop] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        leading = re.match(r"^(\d{1,2})\s", stripped)
        if not leading:
            continue
        ttl = int(leading.group(1))
        if ttl > max_hops:
            continue
        rest = stripped[leading.end():]
        ip_match = _HOP_IP.search(rest)
        rtts = [float(m) for m in _HOP_RTT.findall(rest)]
        hops.append(
            Hop(
                ttl=ttl,
                ip=ip_match.group(1) if ip_match else None,
                rtt_ms=min(rtts) if rtts else None,
            )
        )
    return hops


def classify_topology(hops: list[Hop]) -> Topology:
    """Deduce la topología a partir de los saltos.

    - 1 salto privado  -> este equipo cuelga directo del router principal.
    - 2+ saltos privados -> hay un router intermedio haciendo NAT (doble NAT).
    """
    private_hops: list[str] = []
    for hop in hops:
        if hop.is_private and hop.ip:
            if hop.ip not in private_hops:
                private_hops.append(hop.ip)
        elif hop.ip:
            # Primer salto no privado: se acabó la red interna.
            break

    behind_cgnat = any(hop.is_cgnat for hop in hops)

    if not private_hops:
        kind = "unknown"
        summary = "No se pudo determinar la topología (traceroute sin respuesta)."
    elif len(private_hops) == 1:
        kind = "direct"
        summary = (
            f"Estás conectado directamente al router principal ({private_hops[0]}). "
            "No hay routers intermedios."
        )
    else:
        kind = "cascade"
        summary = (
            f"Hay {len(private_hops)} routers en cascada (doble NAT): "
            + " → ".join(private_hops)
            + f". Tu equipo cuelga de {private_hops[0]}."
        )

    if behind_cgnat:
        summary += (
            " Tu operador usa CGNAT: la IP pública es compartida y no puedes "
            "recibir conexiones entrantes desde internet."
        )

    return Topology(
        kind=kind,
        private_hops=private_hops,
        behind_cgnat=behind_cgnat,
        hops=hops,
        summary=summary,
    )


async def detect_topology(target: str = "8.8.8.8", max_hops: int = 5) -> Topology:
    if IS_WINDOWS:
        cmd = ["tracert", "-d", "-h", str(max_hops), "-w", "500", target]
    else:
        cmd = ["traceroute", "-n", "-m", str(max_hops), "-w", "1", target]
    output = await run(cmd, timeout=45.0)
    return classify_topology(parse_traceroute(output, max_hops))
