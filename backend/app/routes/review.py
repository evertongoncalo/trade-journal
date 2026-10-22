"""Revisão do acerto: o diário e as respostas dos alertas recortados por mercado, setup, decisão, bloco e lente."""
from __future__ import annotations

from fastapi import APIRouter

from .. import db
from ..alerts import store as alert_store
from ..review import engine
from ..util import clean_json

router = APIRouter(prefix="/review", tags=["revisão"])


@router.get("")
def review():
    return clean_json(engine.build(db.all_entries(), alert_store.list_all(limit=1_000_000)))
