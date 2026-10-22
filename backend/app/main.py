"""Aplicação FastAPI: API em /api e, se compilado, o frontend React na raiz."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, db
from .alerts import watcher
from .routes import ai, alerts, assets, correlation, journal, scanner
from .scanner import store as scanner_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    scanner_store.ensure_default_setups()
    scanner_store.close_orphan_runs()
    if config.ALERTS_WATCHER:
        watcher.start()
    yield
    watcher.stop()


app = FastAPI(title="Trade Journal", lifespan=lifespan)
app.include_router(assets.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(correlation.router, prefix="/api")
app.include_router(scanner.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(ai.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


if config.FRONTEND_DIST.is_dir():  # montado por último: as rotas /api têm prioridade
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
