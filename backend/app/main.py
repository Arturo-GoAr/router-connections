"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__, scheduler
from .api import api_router, ws
from .config import BASE_DIR, settings
from .db import init_db
from .scanner import oui, orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


async def _warm_up() -> None:
    """Tareas de arranque que no deben bloquear la respuesta del servidor."""
    try:
        await oui.refresh_from_ieee()
    except Exception:
        log.exception("No se pudo refrescar el catálogo OUI")

    if settings.scan_on_startup:
        try:
            await orchestrator.run_scan()
        except Exception:
            log.exception("El barrido inicial falló")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    # El barrido inicial tarda unos segundos; lanzarlo en segundo plano permite
    # que la interfaz cargue de inmediato y se vaya poblando por WebSocket.
    warm_up_task = asyncio.create_task(_warm_up())

    yield

    warm_up_task.cancel()
    scheduler.shutdown()


app = FastAPI(
    title="Router Connections",
    description=(
        "Inventario y monitoreo de la red local: descubre dispositivos, los "
        "clasifica, escanea sus puertos y gestiona redirecciones en el router."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws.router)


@app.get("/health", tags=["salud"])
async def health() -> dict:
    return {"status": "ok", "version": __version__}


# El frontend compilado se sirve desde el propio backend, de modo que arrancar
# la aplicación sea un único proceso en un único puerto. Este montaje va al
# final a propósito: al colgar de "/" haría sombra a cualquier ruta registrada
# después, y las de la API tienen que ganar.
#
# En desarrollo (`npm run dev`) esta carpeta no existe y no pasa nada: Vite
# sirve el frontend en el 5173 y hace proxy de /api hacia aquí.
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    log.info("Sirviendo el frontend compilado desde %s", FRONTEND_DIST)
else:
    log.info(
        "No hay frontend compilado en %s; solo se sirve la API. "
        "Compílalo con 'npm run build' o usa 'npm run dev'.",
        FRONTEND_DIST,
    )
