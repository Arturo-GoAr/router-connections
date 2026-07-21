"""Descubrimiento de nombres y tipos de dispositivo por protocolos de red.

Ninguna de estas técnicas necesita privilegios ni herramientas externas, y cada
una cubre un hueco de las otras:

- **SSDP/UPnP**: televisores, consolas, routers y reproductores anuncian un XML
  con nombre comercial, fabricante y modelo. Es la fuente más rica que hay.
- **mDNS/Bonjour**: equipos Apple, impresoras, Chromecast y NAS publican su
  nombre y los servicios que ofrecen.
- **NetBIOS**: el clásico de Windows; devuelve el nombre del equipo.
- **DNS inverso**: a veces el router mantiene un PTR con el nombre del cliente.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import struct
from dataclasses import dataclass, field
from xml.etree import ElementTree

import httpx

from ..config import settings

log = logging.getLogger(__name__)

SSDP_ADDRESS = "239.255.255.250"
SSDP_PORT = 1900
NETBIOS_PORT = 137


@dataclass
class DiscoveryInfo:
    """Todo lo que se averiguó sobre una IP, venga del protocolo que venga."""

    ip: str
    hostname: str | None = None
    friendly_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    #: URNs de UPnP, p.ej. `urn:schemas-upnp-org:device:MediaRenderer:1`.
    upnp_device_types: list[str] = field(default_factory=list)
    #: Servicios mDNS, p.ej. `_airplay._tcp.local.`.
    mdns_services: list[str] = field(default_factory=list)
    #: Cabeceras SERVER de SSDP, útiles para adivinar el sistema operativo.
    server_banners: list[str] = field(default_factory=list)

    def merge(self, other: "DiscoveryInfo") -> None:
        self.hostname = self.hostname or other.hostname
        self.friendly_name = self.friendly_name or other.friendly_name
        self.manufacturer = self.manufacturer or other.manufacturer
        self.model = self.model or other.model
        for source, target in (
            (other.upnp_device_types, self.upnp_device_types),
            (other.mdns_services, self.mdns_services),
            (other.server_banners, self.server_banners),
        ):
            for item in source:
                if item not in target:
                    target.append(item)


# --------------------------------------------------------------------------
# SSDP / UPnP
# --------------------------------------------------------------------------

M_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDRESS}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: {st}\r\n"
    "\r\n"
)

#: `ssdp:all` trae de todo; los otros dos hacen que routers y media players
#: contesten aunque implementen SSDP a medias.
SEARCH_TARGETS = [
    "ssdp:all",
    "upnp:rootdevice",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
]


def parse_ssdp_headers(payload: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in payload.split("\r\n")[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
    return headers


async def ssdp_search(timeout: float | None = None) -> dict[str, dict]:
    """Lanza M-SEARCH y recolecta respuestas. Devuelve `{ip: {...}}`."""
    timeout = timeout or settings.ssdp_timeout
    loop = asyncio.get_running_loop()
    responses: dict[str, dict] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setblocking(False)

    try:
        for target in SEARCH_TARGETS:
            message = M_SEARCH.format(st=target).encode("ascii")
            try:
                await loop.sock_sendto(sock, message, (SSDP_ADDRESS, SSDP_PORT))
            except OSError as exc:
                log.debug("No se pudo enviar M-SEARCH (%s): %s", target, exc)

        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 4096), timeout=deadline - loop.time()
                )
            except (asyncio.TimeoutError, OSError):
                break
            headers = parse_ssdp_headers(data.decode("utf-8", errors="replace"))
            entry = responses.setdefault(
                addr[0], {"locations": set(), "servers": set(), "types": set()}
            )
            if location := headers.get("location"):
                entry["locations"].add(location)
            if server := headers.get("server"):
                entry["servers"].add(server)
            for key in ("st", "nt"):
                if value := headers.get(key):
                    entry["types"].add(value)
    finally:
        sock.close()

    return responses


def _xml_text(node: ElementTree.Element | None, tag: str) -> str | None:
    """Busca un tag ignorando el namespace, que varía entre fabricantes."""
    if node is None:
        return None
    for child in node.iter():
        if child.tag.rpartition("}")[2] == tag and child.text:
            return child.text.strip()
    return None


async def fetch_upnp_description(client: httpx.AsyncClient, url: str) -> dict:
    """Descarga el XML de descripción de un dispositivo UPnP."""
    try:
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
        log.debug("No se pudo leer la descripción UPnP en %s: %s", url, exc)
        return {}

    return {
        "friendly_name": _xml_text(root, "friendlyName"),
        "manufacturer": _xml_text(root, "manufacturer"),
        "model": _xml_text(root, "modelName"),
        "device_type": _xml_text(root, "deviceType"),
    }


async def discover_ssdp() -> dict[str, DiscoveryInfo]:
    raw = await ssdp_search()
    results: dict[str, DiscoveryInfo] = {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for ip, entry in raw.items():
            info = DiscoveryInfo(ip=ip)
            info.server_banners = sorted(entry["servers"])
            info.upnp_device_types = sorted(
                t for t in entry["types"] if t.startswith("urn:")
            )
            # Una sola descripción por host basta para el nombre comercial.
            for location in sorted(entry["locations"])[:2]:
                description = await fetch_upnp_description(client, location)
                info.friendly_name = info.friendly_name or description.get(
                    "friendly_name"
                )
                info.manufacturer = info.manufacturer or description.get("manufacturer")
                info.model = info.model or description.get("model")
                device_type = description.get("device_type")
                if device_type and device_type not in info.upnp_device_types:
                    info.upnp_device_types.append(device_type)
            results[ip] = info

    log.info("SSDP: %d dispositivos respondieron", len(results))
    return results


# --------------------------------------------------------------------------
# mDNS / Bonjour
# --------------------------------------------------------------------------

async def discover_mdns() -> dict[str, DiscoveryInfo]:
    """Explora los servicios anunciados por mDNS y los agrupa por IP."""
    try:
        from zeroconf import ServiceStateChange, Zeroconf
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except ImportError:  # pragma: no cover - zeroconf es dependencia dura
        log.warning("zeroconf no está instalado; se omite el descubrimiento mDNS")
        return {}

    results: dict[str, DiscoveryInfo] = {}
    pending: list[asyncio.Task] = []

    async def resolve(zeroconf: Zeroconf, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        try:
            if not await info.async_request(zeroconf, 3000):
                return
        except Exception as exc:  # la librería lanza tipos variados
            log.debug("mDNS: fallo resolviendo %s: %s", name, exc)
            return

        for address in info.parsed_scoped_addresses():
            if ":" in address:  # ignoramos IPv6
                continue
            entry = results.setdefault(address, DiscoveryInfo(ip=address))
            if service_type not in entry.mdns_services:
                entry.mdns_services.append(service_type)
            if info.server:
                entry.hostname = entry.hostname or info.server.rstrip(".").removesuffix(
                    ".local"
                )
            # El nombre de instancia suele ser legible: "Sala de TV._airplay._tcp".
            instance = name.split(".")[0].replace("\\032", " ")
            if instance and not entry.friendly_name:
                entry.friendly_name = instance

    def on_change(zeroconf, service_type, name, state_change, **_kwargs) -> None:
        if state_change is ServiceStateChange.Added:
            pending.append(asyncio.create_task(resolve(zeroconf, service_type, name)))

    aiozc = AsyncZeroconf()
    try:
        # Primero preguntamos qué tipos de servicio existen en esta red, y luego
        # exploramos cada uno; así no dependemos de una lista fija.
        types_found: set[str] = set()

        def on_type(zeroconf, service_type, name, state_change, **_kwargs) -> None:
            if state_change is ServiceStateChange.Added:
                types_found.add(name)

        meta_browser = AsyncServiceBrowser(
            aiozc.zeroconf, "_services._dns-sd._udp.local.", handlers=[on_type]
        )
        await asyncio.sleep(settings.mdns_timeout / 2)
        await meta_browser.async_cancel()

        if types_found:
            browser = AsyncServiceBrowser(
                aiozc.zeroconf, sorted(types_found), handlers=[on_change]
            )
            await asyncio.sleep(settings.mdns_timeout)
            await browser.async_cancel()

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        await aiozc.async_close()

    log.info("mDNS: %d dispositivos con servicios anunciados", len(results))
    return results


# --------------------------------------------------------------------------
# NetBIOS (NBNS)
# --------------------------------------------------------------------------

def build_nbstat_query() -> bytes:
    """Construye un NBSTAT node status request para el nombre comodín '*'.

    El nombre NetBIOS se codifica en 'first-level encoding': cada byte se parte
    en dos nibbles y a cada uno se le suma el valor de 'A'.
    """
    name = b"*" + b"\x00" * 15
    encoded = bytearray()
    for byte in name:
        encoded.append((byte >> 4) + 0x41)
        encoded.append((byte & 0x0F) + 0x41)

    header = struct.pack(
        ">HHHHHH",
        0x4E42,  # transaction id arbitrario
        0x0000,  # flags: query estándar, sin recursión
        1,  # 1 pregunta
        0,
        0,
        0,
    )
    question = bytes([len(encoded)]) + bytes(encoded) + b"\x00"
    question += struct.pack(">HH", 0x0021, 0x0001)  # NBSTAT, IN
    return header + question


def parse_nbstat_response(data: bytes) -> str | None:
    """Extrae el nombre del equipo de una respuesta NBSTAT."""
    if len(data) < 57:
        return None
    offset = 12
    # Saltamos el nombre codificado de la respuesta.
    while offset < len(data) and data[offset] != 0:
        offset += data[offset] + 1
    offset += 1
    offset += 10  # type(2) + class(2) + ttl(4) + rdlength(2)
    if offset >= len(data):
        return None

    name_count = data[offset]
    offset += 1
    for _ in range(name_count):
        if offset + 18 > len(data):
            break
        raw_name = data[offset : offset + 15]
        suffix = data[offset + 15]
        flags = struct.unpack(">H", data[offset + 16 : offset + 18])[0]
        offset += 18
        is_group = bool(flags & 0x8000)
        # Sufijo 0x00 y no-grupo = nombre del equipo (workstation service).
        if suffix == 0x00 and not is_group:
            name = raw_name.decode("ascii", errors="replace").strip()
            if name and name != "*":
                return name
    return None


class _NetbiosProtocol(asyncio.DatagramProtocol):
    def __init__(self, results: dict[str, str]) -> None:
        self.results = results

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        name = parse_nbstat_response(data)
        if name:
            self.results[addr[0]] = name

    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        log.debug("NetBIOS: %s", exc)


async def discover_netbios(ips: list[str]) -> dict[str, str]:
    """Pregunta el nombre NetBIOS a cada IP. Devuelve `{ip: nombre}`."""
    if not ips:
        return {}

    loop = asyncio.get_running_loop()
    results: dict[str, str] = {}
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _NetbiosProtocol(results), local_addr=("0.0.0.0", 0)
    )
    query = build_nbstat_query()
    try:
        for ip in ips:
            try:
                transport.sendto(query, (ip, NETBIOS_PORT))
            except OSError:
                continue
        await asyncio.sleep(settings.netbios_timeout)
    finally:
        transport.close()

    log.info("NetBIOS: %d nombres resueltos", len(results))
    return results


# --------------------------------------------------------------------------
# DNS inverso
# --------------------------------------------------------------------------

_UNHELPFUL_PTR = re.compile(r"^\d{1,3}(-|\.)\d{1,3}")


async def reverse_dns(ips: list[str]) -> dict[str, str]:
    """PTR de cada IP, descartando nombres que solo repiten la propia IP."""
    loop = asyncio.get_running_loop()

    async def resolve(ip: str) -> tuple[str, str | None]:
        try:
            host, _, _ = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyaddr, ip), timeout=2.0
            )
        except (OSError, asyncio.TimeoutError):
            return ip, None
        if host == ip or _UNHELPFUL_PTR.match(host):
            return ip, None
        return ip, host.removesuffix(".local").removesuffix(".lan")

    pairs = await asyncio.gather(*(resolve(ip) for ip in ips))
    return {ip: name for ip, name in pairs if name}


# --------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------

async def discover_all(ips: list[str]) -> dict[str, DiscoveryInfo]:
    """Lanza todas las técnicas en paralelo y fusiona los resultados por IP."""
    ssdp_task = asyncio.create_task(discover_ssdp())
    mdns_task = asyncio.create_task(discover_mdns())
    netbios_task = asyncio.create_task(discover_netbios(ips))
    dns_task = asyncio.create_task(reverse_dns(ips))

    ssdp, mdns, netbios, dns = await asyncio.gather(
        ssdp_task, mdns_task, netbios_task, dns_task, return_exceptions=True
    )

    merged: dict[str, DiscoveryInfo] = {ip: DiscoveryInfo(ip=ip) for ip in ips}

    for source in (ssdp, mdns):
        if isinstance(source, BaseException):
            log.warning("Una fuente de descubrimiento falló: %s", source)
            continue
        for ip, info in source.items():
            merged.setdefault(ip, DiscoveryInfo(ip=ip)).merge(info)

    for source in (netbios, dns):
        if isinstance(source, BaseException):
            log.warning("Una fuente de nombres falló: %s", source)
            continue
        for ip, name in source.items():
            entry = merged.setdefault(ip, DiscoveryInfo(ip=ip))
            entry.hostname = entry.hostname or name

    return merged
