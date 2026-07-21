"""Resolución de fabricante a partir del OUI (los 3 primeros bytes de la MAC).

Estrategia en tres niveles:

1. Un catálogo mínimo embarcado en el repo (`data/oui_fallback.json`), para que
   la app diga algo útil sin red y sin descargas.
2. La base completa del IEEE, descargada bajo demanda y cacheada en disco.
3. Si la MAC es aleatoria (bit locally-administered), no se intenta nada: el
   OUI no significa nada en ese caso, y decir un fabricante sería mentir.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from ..config import DATA_DIR
from .macaddr import is_locally_administered, oui_key

log = logging.getLogger(__name__)

IEEE_OUI_URL = "https://standards-oui.ieee.org/oui/oui.csv"

BUNDLED_PATH = Path(__file__).resolve().parent.parent / "data" / "oui_fallback.json"
CACHE_PATH = DATA_DIR / "oui_ieee.json"

#: Cada cuánto se considera obsoleta la copia descargada del IEEE.
CACHE_TTL = timedelta(days=30)

_registry: dict[str, str] | None = None


def _load_json(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _registry_data() -> dict[str, str]:
    """Catálogo en memoria: el embarcado, sobrescrito por el del IEEE si existe."""
    global _registry
    if _registry is None:
        _registry = _load_json(BUNDLED_PATH)
        _registry.update(_load_json(CACHE_PATH))
        log.info("Catálogo OUI cargado con %d prefijos", len(_registry))
    return _registry


def lookup(mac: str | None) -> str | None:
    """Devuelve el fabricante, o None si no se sabe o la MAC es aleatoria."""
    if not mac:
        return None
    if is_locally_administered(mac):
        return None
    return _registry_data().get(oui_key(mac))


def cache_age() -> timedelta | None:
    if not CACHE_PATH.exists():
        return None
    modified = datetime.fromtimestamp(CACHE_PATH.stat().st_mtime)
    return datetime.now() - modified


def cache_is_fresh() -> bool:
    age = cache_age()
    return age is not None and age < CACHE_TTL


def parse_ieee_csv(text: str) -> dict[str, str]:
    """Convierte el CSV del IEEE en `{"AABBCC": "Nombre del fabricante"}`."""
    registry: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        assignment = (row.get("Assignment") or "").strip().upper()
        organization = (row.get("Organization Name") or "").strip()
        if len(assignment) == 6 and organization:
            registry[assignment] = organization
    return registry


async def refresh_from_ieee(force: bool = False) -> int:
    """Descarga la base del IEEE y la cachea. Devuelve cuántos prefijos hay.

    Es la única descarga externa que hace el escáner, y falla en silencio: si no
    hay internet seguimos con el catálogo embarcado.
    """
    global _registry
    if not force and cache_is_fresh():
        return len(_registry_data())

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(IEEE_OUI_URL)
            response.raise_for_status()
            registry = parse_ieee_csv(response.text)
    except httpx.HTTPError as exc:
        log.warning("No se pudo actualizar el catálogo OUI del IEEE: %s", exc)
        return len(_registry_data())

    if not registry:
        log.warning("El CSV del IEEE llegó vacío o con formato inesperado")
        return len(_registry_data())

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, ensure_ascii=False)

    _registry = None  # fuerza recarga en el próximo lookup
    log.info("Catálogo OUI actualizado: %d prefijos", len(registry))
    return len(registry)
