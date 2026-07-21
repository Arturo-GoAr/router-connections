"""Cliente UPnP IGD para gestionar redirecciones de puerto en el router.

Implementa a mano el diálogo con el router porque el protocolo es simple y así
el proyecto no depende de librerías extra:

1. SSDP M-SEARCH buscando un `InternetGatewayDevice`.
2. Descarga del XML de descripción y localización del servicio
   `WANIPConnection` o `WANPPPConnection`, que es quien gestiona el NAT.
3. Llamadas SOAP a ese servicio para listar, crear y borrar mapeos.

Muchos routers domésticos traen UPnP desactivado de fábrica. Cuando pasa, el
descubrimiento devuelve `None` y la API lo reporta como "no disponible" con una
explicación, en vez de fallar de forma opaca.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import httpx

from ..scanner.discovery import parse_ssdp_headers

log = logging.getLogger(__name__)

SSDP_ADDRESS = "239.255.255.250"
SSDP_PORT = 1900

IGD_SEARCH_TARGETS = [
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
]

#: Servicios que exponen el control del NAT, por orden de preferencia.
WAN_SERVICE_TYPES = [
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANIPConnection:2",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
]

SOAP_ENVELOPE = (
    '<?xml version="1.0"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    "<s:Body><u:{action} xmlns:u=\"{service_type}\">{arguments}</u:{action}></s:Body>"
    "</s:Envelope>"
)


class UpnpError(RuntimeError):
    """Fallo al hablar con el router por UPnP."""


@dataclass(slots=True)
class PortMapping:
    external_port: int
    internal_port: int
    internal_client: str
    protocol: str
    description: str
    enabled: bool
    lease_duration: int = 0
    remote_host: str = ""


@dataclass(slots=True)
class Gateway:
    """Un router que responde a UPnP y expone control del NAT."""

    location: str
    control_url: str
    service_type: str
    friendly_name: str | None = None
    model: str | None = None
    manufacturer: str | None = None


def _local_tag(element: ElementTree.Element) -> str:
    return element.tag.rpartition("}")[2]


async def _search_igd(timeout: float = 3.0) -> list[str]:
    """Devuelve las URLs de descripción (LOCATION) de los IGD que respondan."""
    loop = asyncio.get_running_loop()
    locations: list[str] = []

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setblocking(False)

    try:
        for target in IGD_SEARCH_TARGETS:
            message = (
                "M-SEARCH * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDRESS}:{SSDP_PORT}\r\n"
                'MAN: "ssdp:discover"\r\n'
                "MX: 2\r\n"
                f"ST: {target}\r\n\r\n"
            ).encode("ascii")
            try:
                await loop.sock_sendto(sock, message, (SSDP_ADDRESS, SSDP_PORT))
            except OSError as exc:
                log.debug("No se pudo enviar M-SEARCH de IGD: %s", exc)

        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                data, _ = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 4096), timeout=deadline - loop.time()
                )
            except (asyncio.TimeoutError, OSError):
                break
            headers = parse_ssdp_headers(data.decode("utf-8", errors="replace"))
            location = headers.get("location")
            if location and location not in locations:
                locations.append(location)
    finally:
        sock.close()

    return locations


def _find_wan_service(root: ElementTree.Element) -> tuple[str, str] | None:
    """Localiza el servicio de control del NAT dentro del XML de descripción.

    Devuelve `(service_type, control_url_relativa)`.
    """
    services: dict[str, str] = {}
    for element in root.iter():
        if _local_tag(element) != "service":
            continue
        service_type = None
        control_url = None
        for child in element:
            tag = _local_tag(child)
            if tag == "serviceType":
                service_type = (child.text or "").strip()
            elif tag == "controlURL":
                control_url = (child.text or "").strip()
        if service_type and control_url:
            services[service_type] = control_url

    for preferred in WAN_SERVICE_TYPES:
        if preferred in services:
            return preferred, services[preferred]
    return None


async def discover_gateway(timeout: float = 3.0) -> Gateway | None:
    """Encuentra el primer router que acepte controlar el NAT por UPnP."""
    locations = await _search_igd(timeout)
    if not locations:
        log.info("Ningún router respondió al descubrimiento UPnP")
        return None

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        for location in locations:
            try:
                response = await client.get(location)
                response.raise_for_status()
                root = ElementTree.fromstring(response.content)
            except (httpx.HTTPError, ElementTree.ParseError) as exc:
                log.debug("Descripción UPnP ilegible en %s: %s", location, exc)
                continue

            service = _find_wan_service(root)
            if not service:
                continue
            service_type, control_path = service

            base = urlparse(location)
            control_url = urljoin(f"{base.scheme}://{base.netloc}", control_path)

            def text_of(tag: str) -> str | None:
                for element in root.iter():
                    if _local_tag(element) == tag and element.text:
                        return element.text.strip()
                return None

            return Gateway(
                location=location,
                control_url=control_url,
                service_type=service_type,
                friendly_name=text_of("friendlyName"),
                model=text_of("modelName"),
                manufacturer=text_of("manufacturer"),
            )

    log.info("Se encontraron IGD pero ninguno expone control del NAT")
    return None


async def _soap(
    gateway: Gateway, action: str, arguments: dict[str, str | int] | None = None
) -> dict[str, str]:
    """Ejecuta una acción SOAP y devuelve los argumentos de salida."""
    argument_xml = "".join(
        f"<{name}>{escape(str(value))}</{name}>"
        for name, value in (arguments or {}).items()
    )
    body = SOAP_ENVELOPE.format(
        action=action, service_type=gateway.service_type, arguments=argument_xml
    )
    headers = {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": f'"{gateway.service_type}#{action}"',
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                gateway.control_url, content=body.encode("utf-8"), headers=headers
            )
        except httpx.HTTPError as exc:
            raise UpnpError(f"No se pudo contactar al router: {exc}") from exc

    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as exc:
        raise UpnpError("El router devolvió una respuesta ilegible") from exc

    if response.status_code >= 400:
        raise UpnpError(_describe_soap_fault(root, response.status_code))

    result: dict[str, str] = {}
    for element in root.iter():
        tag = _local_tag(element)
        if tag.startswith("New") and element.text is not None:
            result[tag] = element.text.strip()
    return result


#: Códigos de error del estándar IGD traducidos a algo que el usuario entienda.
UPNP_ERRORS = {
    "402": "El router rechazó los parámetros enviados.",
    "501": "El router no pudo completar la acción.",
    "606": "El router no autoriza esta acción (UPnP en modo solo lectura).",
    "713": "No existe una redirección en esa posición.",
    "714": "No existe esa redirección de puerto.",
    "715": "El router exige especificar el host remoto.",
    "716": "El router exige especificar el puerto externo.",
    "718": "Ese puerto externo ya está ocupado por otra redirección.",
    "724": "El router no permite rangos de puertos con valores distintos.",
    "725": "El router solo acepta redirecciones permanentes.",
    "726": "El router no admite comodines en el host remoto.",
    "727": "El router exige que el puerto externo e interno coincidan.",
}


def _describe_soap_fault(root: ElementTree.Element, status_code: int) -> str:
    code = None
    description = None
    for element in root.iter():
        tag = _local_tag(element)
        if tag == "errorCode":
            code = (element.text or "").strip()
        elif tag == "errorDescription":
            description = (element.text or "").strip()

    if code:
        friendly = UPNP_ERRORS.get(code, description or "Error desconocido")
        return f"{friendly} (código UPnP {code})"
    return f"El router respondió con HTTP {status_code}"


async def get_external_ip(gateway: Gateway) -> str | None:
    result = await _soap(gateway, "GetExternalIPAddress")
    return result.get("NewExternalIPAddress") or None


async def list_mappings(gateway: Gateway, limit: int = 100) -> list[PortMapping]:
    """Enumera las redirecciones activas.

    El estándar IGD no ofrece un "dame todas": hay que pedirlas por índice hasta
    que el router responde con error 713 (no hay más).
    """
    mappings: list[PortMapping] = []
    for index in range(limit):
        try:
            result = await _soap(
                gateway, "GetGenericPortMappingEntry", {"NewPortMappingIndex": index}
            )
        except UpnpError as exc:
            if "713" in str(exc) or "714" in str(exc):
                break  # fin de la lista, no es un fallo
            log.debug("Se detuvo la enumeración de mapeos en el índice %d: %s", index, exc)
            break

        if not result.get("NewExternalPort"):
            break

        mappings.append(
            PortMapping(
                external_port=int(result.get("NewExternalPort", 0)),
                internal_port=int(result.get("NewInternalPort", 0)),
                internal_client=result.get("NewInternalClient", ""),
                protocol=result.get("NewProtocol", "TCP"),
                description=result.get("NewPortMappingDescription", ""),
                enabled=result.get("NewEnabled", "1") == "1",
                lease_duration=int(result.get("NewLeaseDuration", 0) or 0),
                remote_host=result.get("NewRemoteHost", ""),
            )
        )
    return mappings


async def add_mapping(
    gateway: Gateway,
    external_port: int,
    internal_port: int,
    internal_client: str,
    protocol: str = "TCP",
    description: str = "Router Connections",
    lease_duration: int = 0,
) -> None:
    """Crea una redirección de puerto. `lease_duration=0` significa permanente."""
    await _soap(
        gateway,
        "AddPortMapping",
        {
            "NewRemoteHost": "",
            "NewExternalPort": external_port,
            "NewProtocol": protocol.upper(),
            "NewInternalPort": internal_port,
            "NewInternalClient": internal_client,
            "NewEnabled": 1,
            "NewPortMappingDescription": description,
            "NewLeaseDuration": lease_duration,
        },
    )


async def delete_mapping(
    gateway: Gateway, external_port: int, protocol: str = "TCP"
) -> None:
    await _soap(
        gateway,
        "DeletePortMapping",
        {
            "NewRemoteHost": "",
            "NewExternalPort": external_port,
            "NewProtocol": protocol.upper(),
        },
    )
