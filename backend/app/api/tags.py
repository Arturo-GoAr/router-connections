"""CRUD de etiquetas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Tag
from ..schemas import TagCreate, TagRead

router = APIRouter(prefix="/tags", tags=["etiquetas"])


@router.get("", response_model=list[TagRead])
def list_tags(session: Session = Depends(get_session)) -> list[Tag]:
    return session.exec(select(Tag).order_by(Tag.name)).all()


@router.post("", response_model=TagRead, status_code=201)
def create_tag(payload: TagCreate, session: Session = Depends(get_session)) -> Tag:
    existing = session.exec(select(Tag).where(Tag.name == payload.name)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe una etiqueta con ese nombre")

    tag = Tag(name=payload.name, color=payload.color)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204, response_model=None)
def delete_tag(tag_id: int, session: Session = Depends(get_session)) -> None:
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    session.delete(tag)
    session.commit()
