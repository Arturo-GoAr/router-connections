"""Barridos periódicos en segundo plano."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .scanner import orchestrator

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _scheduled_scan() -> None:
    try:
        await orchestrator.run_scan()
    except Exception:  # el scheduler debe sobrevivir a cualquier fallo
        log.exception("El barrido programado falló")


def start() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _scheduled_scan,
        trigger="interval",
        seconds=settings.scan_interval_seconds,
        id="periodic_sweep",
        max_instances=1,
        coalesce=True,  # si nos retrasamos, un solo barrido en vez de una ráfaga
        replace_existing=True,
    )
    scheduler.start()
    log.info("Barrido programado cada %d segundos", settings.scan_interval_seconds)


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
