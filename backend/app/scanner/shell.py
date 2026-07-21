"""Ejecución de comandos del sistema con decodificación tolerante.

La consola de Windows en español devuelve texto en la codepage local (cp850 /
cp1252), no UTF-8, así que decodificamos con varios intentos antes de rendirnos.
"""

from __future__ import annotations

import asyncio
import json
import locale
import logging
import subprocess
import sys
from typing import Any

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

#: Evita que aparezca una ventana de consola al lanzar procesos en Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def _decode(raw: bytes) -> str:
    encodings = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings += ["cp1252", "cp850", "latin-1"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


async def run(cmd: list[str], timeout: float = 20.0) -> str:
    """Ejecuta un comando y devuelve stdout. Cadena vacía si falla."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
    except (FileNotFoundError, NotImplementedError, OSError) as exc:
        log.debug("No se pudo lanzar %s: %s", cmd[0], exc)
        return ""

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        log.debug("Timeout ejecutando %s", " ".join(cmd))
        proc.kill()
        await proc.wait()
        return ""
    return _decode(stdout)


async def powershell_json(script: str, timeout: float = 25.0) -> Any:
    """Ejecuta un script de PowerShell que emite JSON y lo parsea.

    `ConvertTo-Json` colapsa una lista de un solo elemento en un objeto suelto,
    por eso el llamador debe tolerar tanto `dict` como `list`.
    """
    if not IS_WINDOWS:
        return None
    out = await run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )
    out = out.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        log.debug("Salida de PowerShell no era JSON: %.200s", out)
        return None


def as_list(value: Any) -> list[Any]:
    """Normaliza la salida de `ConvertTo-Json` a lista."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
