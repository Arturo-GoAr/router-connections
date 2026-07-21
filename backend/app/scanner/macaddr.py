"""Utilidades de direcciones MAC."""

from __future__ import annotations

import re

_HEX_ONLY = re.compile(r"[^0-9a-f]")

#: MACs que nunca corresponden a un dispositivo real de la red.
_BOGUS = {"000000000000", "ffffffffffff"}


def normalize_mac(raw: str | None) -> str | None:
    """Lleva cualquier formato (`AA-BB-CC`, `aabb.ccdd`, `AA:BB:...`) a `aa:bb:cc:...`."""
    if not raw:
        return None
    hexchars = _HEX_ONLY.sub("", raw.lower())
    if len(hexchars) != 12 or hexchars in _BOGUS:
        return None
    return ":".join(hexchars[i : i + 2] for i in range(0, 12, 2))


def oui_key(mac: str) -> str:
    """Los 3 primeros bytes en mayúsculas sin separadores, como los publica el IEEE."""
    return _HEX_ONLY.sub("", mac.lower())[:6].upper()


def is_locally_administered(mac: str) -> bool:
    """True si el bit 'locally administered' está puesto.

    Es la firma de una MAC aleatoria: iOS y Android la usan por privacidad, así
    que en esos casos el fabricante no se puede deducir del OUI.
    """
    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first_octet & 0b10)


def is_multicast(mac: str) -> bool:
    try:
        return bool(int(mac.split(":")[0], 16) & 0b1)
    except (ValueError, IndexError):
        return False
