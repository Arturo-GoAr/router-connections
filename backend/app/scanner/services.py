"""Catálogo de puertos TCP conocidos y perfiles de escaneo."""

from __future__ import annotations

#: Nombre del servicio que normalmente escucha en cada puerto.
SERVICE_NAMES: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    111: "RPCbind",
    135: "MSRPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    515: "LPD (impresión)",
    548: "AFP",
    554: "RTSP",
    587: "SMTP",
    631: "IPP (impresión)",
    993: "IMAPS",
    995: "POP3S",
    1400: "Sonos",
    1883: "MQTT",
    1900: "SSDP/UPnP",
    2049: "NFS",
    3000: "HTTP alternativo",
    3306: "MySQL",
    3389: "Escritorio remoto",
    5000: "UPnP / HTTP",
    5432: "PostgreSQL",
    5353: "mDNS",
    5555: "ADB / HTTP",
    5900: "VNC",
    6379: "Redis",
    7000: "AirPlay",
    7547: "TR-069 (gestión del ISP)",
    8000: "HTTP alternativo",
    8008: "Chromecast",
    8009: "Chromecast",
    8080: "HTTP proxy",
    8443: "HTTPS alternativo",
    8883: "MQTT sobre TLS",
    9000: "HTTP alternativo",
    9100: "Impresión RAW",
    32400: "Plex",
    49152: "UPnP dinámico",
    62078: "iOS (lockdown)",
}

#: Perfil rápido: lo que basta para identificar un dispositivo doméstico.
QUICK_PORTS: list[int] = [
    21, 22, 23, 53, 80, 135, 139, 443, 445, 515, 554, 631,
    1400, 1900, 3389, 5000, 5555, 5900, 7000, 7547, 8008, 8009,
    8080, 8443, 9100, 32400,
]

#: Perfil estándar: los 100 puertos más habituales más los del perfil rápido.
COMMON_PORTS: list[int] = sorted(
    set(QUICK_PORTS)
    | set(SERVICE_NAMES)
    | {
        20, 69, 88, 123, 161, 389, 636, 993, 995, 1080, 1194, 1433, 1521,
        2000, 2222, 2375, 3128, 3260, 4444, 5001, 5060, 5061, 5222, 5601,
        6000, 6667, 7070, 8081, 8086, 8123, 8200, 8291, 8888, 9090, 9200,
        10000, 27017, 51820,
    }
)

SCAN_PROFILES: dict[str, list[int]] = {
    "quick": QUICK_PORTS,
    "common": COMMON_PORTS,
    "full": list(range(1, 65536)),
}


def service_name(port: int) -> str | None:
    return SERVICE_NAMES.get(port)


def resolve_profile(profile: str) -> list[int]:
    """Devuelve la lista de puertos de un perfil, con `common` por defecto."""
    return SCAN_PROFILES.get(profile, COMMON_PORTS)
