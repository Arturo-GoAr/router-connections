"""Configuración de la aplicación, leída de variables de entorno o .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_prefix="RC_",
        extra="ignore",
    )

    # --- Servidor ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- Base de datos ---
    database_url: str = f"sqlite:///{(DATA_DIR / 'router_connections.db').as_posix()}"

    # --- Escaneo ---
    #: Cada cuánto se lanza un barrido completo de la red, en segundos.
    scan_interval_seconds: int = 300
    #: Lanzar un barrido al arrancar el servidor.
    scan_on_startup: bool = True
    #: Sondeos ARP simultáneos durante el barrido.
    sweep_concurrency: int = 256
    #: Timeout por host al leer la tabla ARP tras el sondeo, en segundos.
    sweep_settle_seconds: float = 2.0
    #: Conexiones TCP simultáneas al escanear puertos.
    port_scan_concurrency: int = 200
    #: Timeout de cada intento de conexión TCP, en segundos.
    port_scan_timeout: float = 1.0
    #: Escanear puertos automáticamente en cada barrido programado.
    port_scan_on_sweep: bool = False
    #: Minutos sin ver un dispositivo antes de marcarlo como desconectado.
    offline_grace_minutes: int = 10

    # --- Descubrimiento ---
    mdns_timeout: float = 4.0
    ssdp_timeout: float = 4.0
    netbios_timeout: float = 1.5

    # --- Red externa ---
    #: Consultar la IP pública a un servicio externo. Desactívalo si prefieres
    #: que la app no haga ninguna petición fuera de tu red.
    enable_public_ip_lookup: bool = True
    public_ip_service: str = "https://api.ipify.org"

    # --- Gestión de puertos ---
    enable_upnp: bool = True
    enable_windows_firewall: bool = True


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
