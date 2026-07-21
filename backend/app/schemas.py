"""Esquemas Pydantic de entrada y salida de la API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .models import DeviceCategory


# --- Dispositivos ----------------------------------------------------------

class TagRead(BaseModel):
    id: int
    name: str
    color: str


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = "#64748b"

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("La etiqueta necesita un nombre")
        return cleaned


class PortRead(BaseModel):
    id: int
    port: int
    protocol: str
    state: str
    service: str | None = None
    banner: str | None = None
    first_seen: datetime
    last_seen: datetime


class SessionRead(BaseModel):
    id: int
    ip: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float


class DeviceRead(BaseModel):
    id: int
    mac: str
    ip: str | None = None
    display_name: str
    hostname: str | None = None
    friendly_name: str | None = None
    alias: str | None = None
    vendor: str | None = None
    model: str | None = None
    category: DeviceCategory
    detected_category: DeviceCategory
    category_override: DeviceCategory | None = None
    detection_reason: str | None = None
    detection_confidence: float
    notes: str | None = None
    is_favorite: bool
    is_gateway: bool
    is_self: bool
    is_online: bool
    first_seen: datetime
    last_seen: datetime
    last_port_scan: datetime | None = None
    #: Segundos desde que empezó la sesión de conexión abierta, si la hay.
    connected_since: datetime | None = None
    uptime_seconds: float | None = None
    open_port_count: int = 0
    tags: list[TagRead] = []


class DeviceDetail(DeviceRead):
    ports: list[PortRead] = []
    recent_sessions: list[SessionRead] = []


class DeviceUpdate(BaseModel):
    """Campos que el usuario puede editar. `None` significa 'no tocar'."""

    alias: str | None = None
    notes: str | None = None
    category_override: DeviceCategory | None = None
    is_favorite: bool | None = None
    #: Poner a True para borrar la categoría manual y volver a la detectada.
    clear_category_override: bool = False

    @field_validator("alias")
    @classmethod
    def clean_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


# --- Red -------------------------------------------------------------------

class InterfaceRead(BaseModel):
    name: str
    ip: str
    prefix_length: int
    cidr: str
    mac: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = []


class HopRead(BaseModel):
    ttl: int
    ip: str | None = None
    rtt_ms: float | None = None
    is_private: bool
    is_cgnat: bool


class TopologyRead(BaseModel):
    kind: str
    private_hops: list[str]
    behind_cgnat: bool
    summary: str
    hops: list[HopRead] = []


class Diagnostic(BaseModel):
    """Aviso sobre algo que limita lo que la app puede ver o hacer."""

    level: str  # "info" | "warning"
    title: str
    detail: str


class NetworkRead(BaseModel):
    interface: InterfaceRead | None = None
    public_ip: str | None = None
    topology: TopologyRead | None = None
    network_profile: str | None = None
    is_admin: bool = False
    is_scanning: bool = False
    device_count: int = 0
    online_count: int = 0
    last_scan_at: datetime | None = None
    diagnostics: list[Diagnostic] = []


class ScanRequest(BaseModel):
    scan_ports: bool = False
    port_profile: str = "quick"


class ScanResultRead(BaseModel):
    devices_found: int
    new_devices: int
    went_offline: int
    duration_seconds: float
    errors: list[str] = []


# --- UPnP ------------------------------------------------------------------

class UpnpStatus(BaseModel):
    available: bool
    reason: str | None = None
    router_name: str | None = None
    router_model: str | None = None
    manufacturer: str | None = None
    external_ip: str | None = None


class PortMappingRead(BaseModel):
    external_port: int
    internal_port: int
    internal_client: str
    protocol: str
    description: str
    enabled: bool
    lease_duration: int = 0


class PortMappingCreate(BaseModel):
    external_port: int = Field(ge=1, le=65535)
    internal_port: int = Field(ge=1, le=65535)
    internal_client: str
    protocol: str = "TCP"
    description: str = "Router Connections"
    lease_duration: int = Field(default=0, ge=0, le=604800)

    @field_validator("protocol")
    @classmethod
    def check_protocol(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"TCP", "UDP"}:
            raise ValueError("El protocolo debe ser TCP o UDP")
        return upper


# --- Firewall --------------------------------------------------------------

class FirewallStatus(BaseModel):
    available: bool
    is_admin: bool
    reason: str | None = None


class FirewallRuleRead(BaseModel):
    name: str
    display_name: str
    direction: str
    action: str
    enabled: bool
    protocol: str | None = None
    local_ports: str | None = None
    profile: str | None = None
    description: str | None = None
    managed: bool


class FirewallRuleCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    ports: str
    protocol: str = "TCP"
    direction: str = "Inbound"
    action: str = "Allow"
    description: str = ""
