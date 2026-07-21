"""Modelos de base de datos (SQLModel / SQLite).

El identificador estable de un dispositivo es su MAC, no su IP: el DHCP puede
reasignar direcciones, pero la MAC sobrevive entre reinicios. Toda la historia
(sesiones, puertos, etiquetas) cuelga de la MAC.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

# Ojo: este módulo NO usa `from __future__ import annotations`. SQLAlchemy
# necesita resolver las anotaciones de las relaciones en tiempo de ejecución, y
# con las anotaciones diferidas `list["Device"]` le llega como texto sin
# resolver y falla al mapear.


def utcnow() -> datetime:
    """`datetime.utcnow` está deprecado; centralizamos el reemplazo aquí."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeviceCategory(str, Enum):
    """Categorías con las que la app clasifica lo que encuentra en la red."""

    ROUTER = "router"
    MODEM = "modem"
    ACCESS_POINT = "access_point"
    PC = "pc"
    LAPTOP = "laptop"
    PHONE = "phone"
    TABLET = "tablet"
    TV = "tv"
    CONSOLE = "console"
    PRINTER = "printer"
    CAMERA = "camera"
    SPEAKER = "speaker"
    NAS = "nas"
    IOT = "iot"
    UNKNOWN = "unknown"


class PortState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class DeviceTagLink(SQLModel, table=True):
    """Tabla puente entre dispositivos y etiquetas."""

    __tablename__ = "device_tag_link"

    device_id: int | None = Field(
        default=None, foreign_key="device.id", primary_key=True
    )
    tag_id: int | None = Field(default=None, foreign_key="tag.id", primary_key=True)


class Tag(SQLModel, table=True):
    """Etiqueta libre que el usuario cuelga de uno o varios dispositivos."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    color: str = "#64748b"
    created_at: datetime = Field(default_factory=utcnow)

    devices: List["Device"] = Relationship(
        back_populates="tags", link_model=DeviceTagLink
    )


class Device(SQLModel, table=True):
    """Un dispositivo visto en la red local, identificado por su MAC."""

    id: Optional[int] = Field(default=None, primary_key=True)

    mac: str = Field(index=True, unique=True, description="MAC normalizada aa:bb:cc:...")
    ip: str | None = Field(default=None, index=True)

    # --- Identidad descubierta automáticamente ---
    hostname: str | None = None
    vendor: str | None = None
    #: Nombre "bonito" reportado por SSDP/mDNS (ej. "Samsung Q60 TV").
    friendly_name: str | None = None
    model: str | None = None
    os_guess: str | None = None
    detected_category: DeviceCategory = DeviceCategory.UNKNOWN
    #: Cómo se llegó a la categoría, para poder explicarlo en la UI.
    detection_reason: str | None = None
    detection_confidence: float = 0.0

    # --- Datos que pone el usuario (siempre ganan sobre lo detectado) ---
    alias: str | None = None
    category_override: DeviceCategory | None = None
    notes: str | None = None
    is_favorite: bool = False

    # --- Estado ---
    is_gateway: bool = False
    is_self: bool = Field(default=False, description="Este mismo equipo")
    is_online: bool = Field(default=True, index=True)
    first_seen: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow, index=True)
    last_port_scan: datetime | None = None

    tags: List[Tag] = Relationship(back_populates="devices", link_model=DeviceTagLink)
    sessions: List["DeviceSession"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    ports: List["PortRecord"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @property
    def display_name(self) -> str:
        return self.alias or self.friendly_name or self.hostname or self.ip or self.mac

    @property
    def category(self) -> DeviceCategory:
        return self.category_override or self.detected_category


class DeviceSession(SQLModel, table=True):
    """Un tramo continuo de tiempo durante el cual el dispositivo estuvo online.

    Es lo que responde "¿desde cuándo está conectado?": la sesión abierta
    (`ended_at is None`) empezó cuando el dispositivo reapareció en la red.
    """

    __tablename__ = "device_session"

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    ip: str | None = None
    started_at: datetime = Field(default_factory=utcnow, index=True)
    ended_at: datetime | None = Field(default=None, index=True)
    #: Último barrido en que se vio; al cerrar la sesión se usa como `ended_at`.
    last_seen: datetime = Field(default_factory=utcnow)

    device: Optional[Device] = Relationship(back_populates="sessions")


class PortRecord(SQLModel, table=True):
    """Resultado del último escaneo de un puerto concreto en un dispositivo."""

    __tablename__ = "port_record"

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    port: int = Field(index=True)
    protocol: str = "tcp"
    state: PortState = PortState.OPEN
    service: str | None = None
    banner: str | None = None
    first_seen: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow)

    device: Optional[Device] = Relationship(back_populates="ports")


class DeviceSignal(SQLModel, table=True):
    """Una señal de descubrimiento observada en un dispositivo.

    Existe porque las señales son **intermitentes**: una TV solo contesta a SSDP
    cuando está encendida, y un móvil solo anuncia mDNS cuando está despierto.
    Si la clasificación usara únicamente lo visto en el último barrido, un
    dispositivo bien identificado se degradaría a "desconocido" en cuanto se
    durmiera. Guardándolas, la evidencia se acumula y la categoría es estable.
    """

    __tablename__ = "device_signal"

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    #: "upnp" | "mdns" | "banner"
    kind: str = Field(index=True)
    value: str
    first_seen: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow)


class ScanRun(SQLModel, table=True):
    """Bitácora de cada barrido, para mostrar actividad reciente en la UI."""

    __tablename__ = "scan_run"

    id: int | None = Field(default=None, primary_key=True)
    kind: str = "sweep"
    started_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None
    devices_found: int = 0
    new_devices: int = 0
    error: str | None = None
