from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.providers import registry
from app.providers.base import PriceHistory
from app.routes import assets


def _ohlc(close, idx):
    return pd.DataFrame(
        {"Open": close, "High": close * 1.004, "Low": close * 0.996, "Close": close, "Volume": 1e6}, index=idx
    )


def fake_fetch(market, symbol, interval, days):
    rng = np.random.default_rng(11)
    now = pd.Timestamp.now(tz="UTC")
    if interval == "1d":
        idx = pd.date_range(end=now.normalize(), periods=900, freq="D")
    else:
        idx = pd.date_range(end=now.floor("h"), periods=100, freq="h")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx))))
    return PriceHistory(_ohlc(close, idx), "fake", symbol, interval)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(registry, "fetch", fake_fetch)
    monkeypatch.setattr(assets, "exchange_of", lambda s: "NMS")
    with TestClient(app) as c:
        yield c


PLAN = dict(
    market="acoes", symbol="nvda", decision="entrei", direction="alta",
    entry_price=100, invalidation=95, target=110, horizon_days=5, thesis="teste",
)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_asset_endpoint(client):
    r = client.get("/api/asset/acoes/nvda?horizon=10")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "NVDA" and body["tradingview_symbol"] == "NASDAQ:NVDA"
    assert 0 <= body["snapshot"]["rsi14"] <= 100
    assert body["probability"]["label"] in {"alta", "baixa", "indistinta", "sem dados"}
    assert body["health"]["daily"]["source"] == "fake"


def test_asset_validation_errors(client):
    assert client.get("/api/asset/bolsa/NVDA").status_code == 422
    assert client.get("/api/asset/forex/EUR").status_code == 422


def test_journal_rejects_inconsistent_plan(client):
    assert client.post("/api/journal", json={**PLAN, "invalidation": 105}).status_code == 422


def test_journal_flow_refresh_marks_target_and_stats(client, monkeypatch):
    created = client.post("/api/journal", json=PLAN)
    assert created.status_code == 201
    entry = created.json()
    assert entry["symbol"] == "NVDA" and entry["status"] == "aberta" and entry["risk"] == 5

    def hits_target(market, symbol, interval, days):
        idx = pd.date_range(datetime.now(timezone.utc) + timedelta(hours=1), periods=2, freq="h")
        df = pd.DataFrame(
            [(100, 102, 99, 101), (101, 111, 100, 110)],
            columns=["Open", "High", "Low", "Close"], index=idx,
        ).assign(Volume=0.0)
        return PriceHistory(df, "fake", symbol, interval)

    monkeypatch.setattr(registry, "fetch", hits_target)
    res = client.post("/api/journal/refresh").json()
    assert res["avaliadas"] == 1 and res["encerradas"] == 1 and res["erros"] == []

    row = client.get("/api/journal").json()[0]
    assert row["status"] == "alvo" and row["r_multiple"] == pytest.approx(2.0)

    stats = client.get("/api/journal/stats").json()
    assert stats["geral"]["taxa_acerto"] == 1.0
    assert stats["por_decisao"]["entrei"]["alvo"] == 1


def test_early_exit(client):
    entry = client.post("/api/journal", json=PLAN).json()
    r = client.post(f"/api/journal/{entry['id']}/early-exit", json={"price": 97, "reason": "price action mudou"})
    assert r.status_code == 200
    assert r.json()["early_exit_r"] == pytest.approx(-0.6)
    assert client.post(f"/api/journal/{entry['id']}/early-exit", json={"price": 98}).status_code == 400

    watched = client.post("/api/journal", json={**PLAN, "decision": "observando"}).json()
    assert client.post(f"/api/journal/{watched['id']}/early-exit", json={"price": 97}).status_code == 400


def test_delete(client):
    entry = client.post("/api/journal", json=PLAN).json()
    assert client.delete(f"/api/journal/{entry['id']}").status_code == 204
    assert client.get("/api/journal").json() == []
    assert client.delete(f"/api/journal/{entry['id']}").status_code == 404
