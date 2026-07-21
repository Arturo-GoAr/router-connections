"""Motor de base de datos y helpers de sesión."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# `check_same_thread=False` porque el scheduler escribe desde un hilo distinto
# al de las peticiones HTTP; SQLite lo permite mientras serialicemos escrituras.
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Importa los modelos para que queden registrados en SQLModel.metadata.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sesión para código fuera de una petición (scheduler, tareas de fondo)."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
