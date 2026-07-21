"""Clasificación heurística de dispositivos por acumulación de indicios.

No existe una señal única que diga "esto es una TV". Lo que hay son pistas
débiles —el fabricante de la MAC, un servicio mDNS, un puerto abierto, el
nombre del host— y este módulo las suma. Cada regla aporta puntos a una
categoría y explica por qué; gana la que más puntos acumula, y la explicación
viaja hasta la UI para que el usuario pueda juzgar si tiene sentido.

Todo esto es una conjetura informada, nunca un hecho: por eso el usuario
siempre puede sobrescribir la categoría desde la interfaz.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..models import DeviceCategory as C

#: Pesos: 5 = casi concluyente, 3 = fuerte, 2 = moderado, 1 = leve.
CONCLUSIVE, STRONG, MODERATE, WEAK = 5, 3, 2, 1


@dataclass(slots=True)
class Evidence:
    """Todo lo que sabemos de un dispositivo en el momento de clasificarlo."""

    mac: str
    vendor: str | None = None
    hostname: str | None = None
    friendly_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    upnp_device_types: list[str] = field(default_factory=list)
    mdns_services: list[str] = field(default_factory=list)
    server_banners: list[str] = field(default_factory=list)
    open_ports: list[int] = field(default_factory=list)
    is_gateway: bool = False
    is_self: bool = False
    #: Topología detectada; ayuda a separar módem de router en cascada.
    topology_kind: str = "unknown"
    #: Posición del dispositivo en la cadena de saltos privados (0 = el más cercano).
    hop_index: int | None = None

    @property
    def text_blob(self) -> str:
        """Todo el texto disponible, en minúsculas, para buscar palabras clave."""
        parts = [
            self.vendor,
            self.hostname,
            self.friendly_name,
            self.manufacturer,
            self.model,
            *self.upnp_device_types,
            *self.mdns_services,
            *self.server_banners,
        ]
        return " ".join(p.lower() for p in parts if p)


@dataclass(slots=True)
class Classification:
    category: C
    confidence: float
    reasons: list[str]

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


# --- Palabras clave por categoría -----------------------------------------
# Se buscan en el texto agregado (fabricante + nombre + servicios + banners).

KEYWORD_RULES: list[tuple[C, int, tuple[str, ...]]] = [
    # "crystal uhd", "qled" y demás son líneas comerciales de televisor: si
    # aparecen en el nombre que anuncia el propio aparato, es una TV.
    (C.TV, STRONG, ("smart tv", "smarttv", "bravia", "roku", "firetv", "fire tv",
                    "chromecast", "android tv", "appletv", "apple tv", "webos",
                    "tizen", "vizio", "hisense", "mediarenderer",
                    "crystal uhd", "qled", "the frame", "nanocell",
                    "dial-multiscreen")),
    # AirPlay a secas no distingue: lo hablan igual un HomePod y un Apple TV,
    # así que aquí solo van servicios que son inequívocamente de altavoz.
    (C.SPEAKER, STRONG, ("sonos", "homepod", "echo dot", "alexa", "soundbar",
                         "spotify-connect", "bose", "nest audio")),
    (C.PRINTER, CONCLUSIVE, ("printer", "impresora", "laserjet", "officejet",
                             "deskjet", "_ipp", "_pdl-datastream", "envy",
                             "ecotank", "workforce", "brother")),
    (C.CAMERA, STRONG, ("camera", "camara", "ipcam", "hikvision", "dahua",
                        "wyze", "ring", "nest cam", "reolink", "tapo")),
    (C.CONSOLE, STRONG, ("playstation", "xbox", "nintendo", "switch")),
    (C.NAS, STRONG, ("synology", "qnap", "diskstation", "truenas", "unraid",
                     "_afpovertcp", "readynas")),
    (C.PHONE, MODERATE, ("iphone", "galaxy", "pixel", "oneplus", "xiaomi",
                         "redmi", "huawei", "android", "moto g")),
    (C.TABLET, MODERATE, ("ipad", "tablet", "galaxy tab")),
    (C.LAPTOP, MODERATE, ("laptop", "macbook", "thinkpad", "notebook",
                          "latitude", "inspiron", "vivobook", "zenbook")),
    (C.PC, MODERATE, ("desktop", "imac", "workstation", "pc-")),
    (C.ROUTER, STRONG, ("router", "gateway", "openwrt", "dd-wrt", "mikrotik",
                        "ubiquiti", "unifi", "internetgatewaydevice")),
    (C.ACCESS_POINT, MODERATE, ("access point", "repeater", "extender",
                                "range extender", "mesh")),
    (C.IOT, WEAK, ("esp32", "esp8266", "espressif", "tuya", "sonoff",
                   "shelly", "tasmota", "_hap")),
]

#: Puertos que apuntan con fuerza a un tipo de dispositivo.
PORT_RULES: list[tuple[C, int, tuple[int, ...], str]] = [
    (C.PRINTER, CONCLUSIVE, (9100, 631, 515), "puertos de impresión abiertos"),
    (C.NAS, STRONG, (5000, 5001, 548, 2049), "servicios de almacenamiento en red"),
    (C.NAS, MODERATE, (32400,), "servidor Plex"),
    (C.CAMERA, MODERATE, (554,), "streaming RTSP"),
    (C.SPEAKER, STRONG, (1400,), "puerto de control de Sonos"),
    (C.TV, MODERATE, (8008, 8009), "receptor Chromecast"),
    (C.PHONE, MODERATE, (62078,), "servicio lockdown de iOS"),
    (C.PC, MODERATE, (3389, 445, 139, 135), "servicios de Windows (SMB/RDP)"),
    (C.PC, WEAK, (22,), "servidor SSH"),
    (C.ROUTER, MODERATE, (53,), "servidor DNS local"),
]

#: Fabricantes cuyo nombre ya sugiere la categoría. Se compara en minúsculas.
VENDOR_RULES: list[tuple[C, int, tuple[str, ...]]] = [
    (C.ROUTER, MODERATE, ("tp-link", "netgear", "d-link", "linksys", "zyxel",
                          "tenda", "netis", "mikrotik", "ubiquiti")),
    (C.MODEM, MODERATE, ("arris", "technicolor", "sagemcom", "sercomm",
                         "commscope", "calix", "actiontec", "askey")),
    (C.PC, WEAK, ("giga-byte", "gigabyte", "asrock", "micro-star", "msi",
                  "intel corporate", "dell inc", "hewlett packard")),
    (C.PHONE, WEAK, ("apple", "samsung electronics", "xiaomi", "oppo", "vivo",
                     "oneplus", "guangdong")),
    (C.IOT, WEAK, ("espressif", "tuya", "shenzhen")),
]


def _score_gateway(evidence: Evidence, scores: dict[C, int], reasons: list[str]) -> None:
    """El gateway es un caso especial: hay que decidir si es módem o router.

    Un equipo del operador con TR-069 (puerto 7547) abierto es casi siempre el
    módem/ONT que administra el ISP. Si en cambio hay routers en cascada, el
    primer salto es tu router y el siguiente el módem.
    """
    if not evidence.is_gateway:
        return

    if 7547 in evidence.open_ports:
        scores[C.MODEM] += CONCLUSIVE
        reasons.append("es tu gateway y expone TR-069, el puerto de gestión del ISP")
    elif evidence.topology_kind == "cascade" and evidence.hop_index == 0:
        scores[C.ROUTER] += CONCLUSIVE
        reasons.append("es tu gateway y hay otro router por encima (doble NAT)")
    else:
        scores[C.ROUTER] += STRONG
        scores[C.MODEM] += WEAK
        reasons.append("es la puerta de enlace de tu red")


def classify(evidence: Evidence) -> Classification:
    """Suma indicios y devuelve la categoría más probable con su explicación."""
    scores: dict[C, int] = defaultdict(int)
    reasons: list[str] = []
    blob = evidence.text_blob

    _score_gateway(evidence, scores, reasons)

    if evidence.is_self:
        scores[C.PC] += CONCLUSIVE
        reasons.append("es este mismo equipo")

    for category, weight, keywords in KEYWORD_RULES:
        matched = [k for k in keywords if k in blob]
        if matched:
            scores[category] += weight
            reasons.append(f"coincide con {', '.join(matched[:3])}")

    vendor = (evidence.vendor or "").lower()
    for category, weight, vendors in VENDOR_RULES:
        if any(v in vendor for v in vendors):
            scores[category] += weight
            reasons.append(f"el fabricante ({evidence.vendor}) suele fabricar esto")

    open_ports = set(evidence.open_ports)
    for category, weight, ports, description in PORT_RULES:
        if open_ports & set(ports):
            scores[category] += weight
            reasons.append(description)

    # Un dispositivo que no es gateway pero se comporta como router es un AP o
    # un router en modo puente colgado de la red.
    if not evidence.is_gateway and scores.get(C.ROUTER, 0) >= STRONG:
        scores[C.ACCESS_POINT] += MODERATE
        reasons.append("parece equipo de red pero no es tu gateway")

    if not scores:
        return Classification(
            category=C.UNKNOWN,
            confidence=0.0,
            reasons=["sin indicios suficientes; solo responde a ARP"],
        )

    best = max(scores.items(), key=lambda item: item[1])
    category, points = best
    runner_up = max(
        (value for key, value in scores.items() if key != category), default=0
    )

    # La confianza crece con los puntos y con la distancia al segundo candidato:
    # un empate entre dos categorías debe reportarse como poco fiable.
    margin = points - runner_up
    confidence = min(0.35 + 0.09 * points + 0.08 * margin, 0.98)

    return Classification(
        category=category, confidence=round(confidence, 2), reasons=reasons
    )
