import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import db
from app.correlation import store, universe
from app.main import app
from app.providers import registry
from app.providers.base import PriceHistory, ProviderError


def _universe_series(n=420, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    m = rng.normal(0.0004, 0.01, n)
    ret = {"^GSPC": m, "DX-Y.NYB": rng.normal(0, 0.004, n), "^VIX": -3 * m + rng.normal(0, 0.01, n)}
    closes = {k: pd.Series(100 * np.cumprod(1 + v), index=idx) for k, v in ret.items()}
    target = pd.Series(100 * np.cumprod(1 + 1.4 * m + rng.normal(0, 0.006, n)), index=idx)
    return closes, target


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setitem(store._status, "state", "idle")
    monkeypatch.setattr(universe, "own_sector_etfs", lambda sym: frozenset())
    with TestClient(app) as c:
        yield c


def patch_target(monkeypatch, target):
    stub = pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-01-01"], tz="UTC"))
    monkeypatch.setattr(registry, "fetch", lambda m, s, i, d: PriceHistory(stub, "fake", s, i))
    monkeypatch.setattr(store, "snap_ny16", lambda df, now=None: target)


def test_panel_without_universe_reports_empty_state(client, monkeypatch):
    _, target = _universe_series()
    patch_target(monkeypatch, target)
    body = client.get("/api/correlation/acoes/nvda").json()
    assert body["universe"]["state"] == "vazio"
    assert [r["status"] for r in body["fixed"]] == ["sem dados", "sem dados"]
    assert body["discovered"] == []
    assert body["target"]["symbol"] == "NVDA" and body["target"]["observations"] == len(target)


def test_panel_with_universe(client, monkeypatch):
    closes, target = _universe_series()
    for sym, s in closes.items():
        store.save_closes(sym, s)
    patch_target(monkeypatch, target)

    body = client.get("/api/correlation/acoes/NVDA").json()
    assert body["universe"]["symbols"] == 3
    spx, dxy = body["fixed"]
    assert spx["symbol"] == "^GSPC" and spx["status"] == "estável" and spx["corr_full"] > 0.6
    assert dxy["status"] == "sem relação estável"
    assert body["parecer"]["lines"] and body["charts"]["rebased"] and body["charts"]["scatter"]
    vix = body["discovered"][0]["items"][0]
    assert vix["symbol"] == "^VIX" and vix["corr_full"] < 0
    assert body["params"]["alignment"] == "16:00 America/New_York"


def test_forex_usd_pair_marks_dxy_as_mechanical(client, monkeypatch):
    closes, target = _universe_series()
    for sym, s in closes.items():
        store.save_closes(sym, s)
    patch_target(monkeypatch, target)
    fixed = client.get("/api/correlation/forex/EURUSD").json()["fixed"]
    assert [r["status"] for r in fixed][1] == "mecânica"


def test_target_equal_to_a_reference_is_excluded(client, monkeypatch):
    closes, target = _universe_series()
    for sym, s in closes.items():
        store.save_closes(sym, s)
    patch_target(monkeypatch, target)
    monkeypatch.setattr("app.correlation.service.yahoo_symbol", lambda m, s: ("^VIX", ""))
    discovered = client.get("/api/correlation/cripto/BTC").json()["discovered"]
    assert all(i["symbol"] != "^VIX" for g in discovered for i in g["items"])


def test_validation_and_provider_errors(client, monkeypatch):
    assert client.get("/api/correlation/forex/EUR").status_code == 422

    def fail(*a, **k):
        raise ProviderError("sem dados")

    monkeypatch.setattr(registry, "fetch", fail)
    assert client.get("/api/correlation/acoes/NVDA").status_code == 502


def test_refresh_and_status_endpoints(client, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "start_refresh", lambda symbols=None: calls.append(1) or True)
    assert client.post("/api/correlation/refresh").json()["started"] is True and calls
    st = client.get("/api/correlation/status").json()
    assert st["universe"]["state"] == "vazio" and "refresh" in st
