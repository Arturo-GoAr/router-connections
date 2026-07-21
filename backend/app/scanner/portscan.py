"""Escaneo de puertos TCP mediante conexión completa (connect scan).

Sin sockets raw no se puede hacer un SYN scan, así que abrimos una conexión TCP
normal y miramos si el handshake completa. Es más ruidoso y más lento que un SYN
scan, pero funciona sin privilegios de administrador, que es el requisito.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..config import settings
from .services import resolve_profile, service_name

log = logging.getLogger(__name__)

#: Puertos donde merece la pena leer el banner para identificar el software.
BANNER_PORTS = {21, 22, 23, 25, 110, 143, 587, 3306, 5432, 6379}

#: Puertos donde una petición HTTP mínima revela cabecera `Server`.
HTTP_PORTS = {80, 443, 591, 3000, 5000, 8000, 8008, 8080, 8081, 8443, 8888, 9000}


@dataclass(slots=True)
class OpenPort:
    port: int
    protocol: str = "tcp"
    service: str | None = None
    banner: str | None = None


async def _grab_banner(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, port: int
) -> str | None:
    """Intenta leer una pista textual del servicio, sin bloquearse si calla."""
    try:
        if port in HTTP_PORTS:
            writer.write(b"HEAD / HTTP/1.0\r\n\r\n")
            await writer.drain()
        data = await asyncio.wait_for(reader.read(256), timeout=1.5)
    except (asyncio.TimeoutError, OSError):
        return None

    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    if port in HTTP_PORTS:
        # De la respuesta HTTP solo nos interesa la cabecera Server.
        for line in text.splitlines():
            if line.lower().startswith("server:"):
                return line.partition(":")[2].strip()[:120]
        return text.splitlines()[0][:120]

    return text.splitlines()[0][:120]


async def probe_port(
    ip: str, port: int, semaphore: asyncio.Semaphore, timeout: float, banners: bool
) -> OpenPort | None:
    """Devuelve `OpenPort` si el puerto acepta conexiones, `None` si no."""
    async with semaphore:
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=timeout
            )
        except (asyncio.TimeoutError, OSError):
            return None

        banner: str | None = None
        if banners and (port in BANNER_PORTS or port in HTTP_PORTS):
            banner = await _grab_banner(reader, writer, port)

        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
        except (asyncio.TimeoutError, OSError):
            pass

        return OpenPort(port=port, service=service_name(port), banner=banner)


async def scan_host(
    ip: str,
    ports: list[int] | None = None,
    profile: str = "common",
    timeout: float | None = None,
    concurrency: int | None = None,
    grab_banners: bool = True,
) -> list[OpenPort]:
    """Escanea un host y devuelve solo los puertos abiertos, ordenados."""
    targets = ports if ports is not None else resolve_profile(profile)
    semaphore = asyncio.Semaphore(concurrency or settings.port_scan_concurrency)
    effective_timeout = timeout or settings.port_scan_timeout

    results = await asyncio.gather(
        *(
            probe_port(ip, port, semaphore, effective_timeout, grab_banners)
            for port in targets
        )
    )
    open_ports = sorted(
        (result for result in results if result is not None), key=lambda p: p.port
    )
    log.info("%s: %d/%d puertos abiertos", ip, len(open_ports), len(targets))
    return open_ports


async def scan_many(
    ips: list[str], profile: str = "quick", host_concurrency: int = 8
) -> dict[str, list[OpenPort]]:
    """Escanea varios hosts limitando cuántos se atacan a la vez."""
    host_semaphore = asyncio.Semaphore(host_concurrency)

    async def one(ip: str) -> tuple[str, list[OpenPort]]:
        async with host_semaphore:
            return ip, await scan_host(ip, profile=profile)

    return dict(await asyncio.gather(*(one(ip) for ip in ips)))
