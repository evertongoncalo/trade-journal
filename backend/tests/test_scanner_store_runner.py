import numpy as np
import pandas as pd
import pytest

from app import db
from app.scanner import data, runner, store, universe
from app.scanner.defaults import DEFAULT_SETUPS, DEFAULT_SETUPS_H4


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setitem(runner._status, "state", "idle")


def ohlcv(n=300, drift=0.003, seed=1):
    rng = np.random.default_rng(seed)
    close = 50 * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": close, "High": close * 1.004, "Low": close * 0.996, "Close": close, "Volume": 5e6}, index=idx
    )


DEF = {"required": [{"type": "trend_up", "params": {}}], "confirmations": [], "min_confirmations": 0}


# ---------- setups ----------


def test_default_setups_are_created_once():
    store.ensure_default_setups()
    store.ensure_default_setups()
    setups = store.list_setups()
    assert [s["name"] for s in setups] == [s["name"] for s in [*DEFAULT_SETUPS, *DEFAULT_SETUPS_H4]]  # D1 e H4
    assert all(s["enabled"] and s["definition"]["filters"]["min_price"] == 5 for s in setups)


def test_setup_crud_normalizes_the_definition():
    s = store.create_setup("Meu setup", True, "alta", ["acoes"], {"required": [{"type": "rsi_between"}]})
    assert s["definition"]["required"][0]["params"] == {"lo": 40.0, "hi": 60.0}  # parâmetros completados
    updated = store.update_setup(s["id"], "Renomeado", False, "baixa", ["forex"], DEF)
    assert updated["name"] == "Renomeado" and updated["enabled"] is False and updated["markets"] == ["forex"]
    assert store.update_setup(999, "x", True, "alta", ["acoes"], DEF) is None
    assert store.delete_setup(s["id"]) is True and store.get_setup(s["id"]) is None and store.delete_setup(s["id"]) is False
    with pytest.raises(ValueError):
        store.create_setup("Ruim", True, "alta", ["acoes"], {"required": [{"type": "nao_existe"}]})


# ---------- varreduras ----------


def test_run_lifecycle_and_hits():
    run_id = store.create_run(["acoes"], [{"name": "A"}])
    assert store.latest_run() is None  # só varreduras concluídas contam
    hit = {
        "setup_id": 1, "setup_name": "A", "market": "acoes", "symbol": "AAA", "direction": "alta",
        "price": 10.0, "details": {"rsi14": 55.0, "required": ["x"]},
    }
    store.save_hits(run_id, [hit])
    store.finish_run(run_id, "done", 10, 9, {"acoes:ZZZ": "sem dados"}, {"acoes": "2026-01-12"})
    latest = store.latest_run()
    assert latest["id"] == run_id and latest["errors_count"] == 1 and latest["as_of"] == {"acoes": "2026-01-12"}
    hits = store.run_hits(run_id)
    assert hits[0]["details"]["rsi14"] == 55.0 and hits[0]["opened_at"] is None
    assert store.mark_hit_opened(hits[0]["id"]) is True
    first_open = store.run_hits(run_id)[0]["opened_at"]
    assert first_open is not None
    store.mark_hit_opened(hits[0]["id"])
    assert store.run_hits(run_id)[0]["opened_at"] == first_open  # a primeira abertura é preservada
    assert store.mark_hit_opened(12345) is False
    assert "errors" not in store.list_runs()[0]


def test_orphan_runs_are_closed_on_startup():
    run_id = store.create_run(["acoes"], [])
    store.close_orphan_runs()
    assert store.get_run(run_id)["state"] == "error" and store.get_run(run_id)["error"] == "interrompida"


def _patch_sources(monkeypatch, frames_by_market, errors_by_market=None):
    monkeypatch.setattr(universe, "symbols_for", lambda m: list(frames_by_market[m]) + list((errors_by_market or {}).get(m, {})))
    monkeypatch.setattr(
        data, "fetch_daily",
        lambda m, syms, progress=None, now=None: (
            (progress and progress(len(syms))) or (frames_by_market[m], (errors_by_market or {}).get(m, {}))
        ),
    )


def test_run_scan_saves_hits_errors_and_as_of(monkeypatch):
    for s in store.list_setups():
        store.delete_setup(s["id"])
    store.create_setup("Tendência", True, "alta", ["acoes", "forex"], DEF)
    up, down = ohlcv(drift=0.003), ohlcv(drift=-0.003, seed=2)
    _patch_sources(
        monkeypatch,
        {"acoes": {"UP": up, "DOWN": down}, "forex": {"EURUSD": up}},
        {"acoes": {"BAD": "sem dados suficientes no Yahoo"}},
    )

    run_id = runner.run_scan(["acoes", "forex"])
    run = store.get_run(run_id)
    assert run["state"] == "done" and run["symbols_total"] == 4 and run["symbols_ok"] == 3
    assert run["errors"] == {"acoes:BAD": "sem dados suficientes no Yahoo"}
    assert run["as_of"] == {"acoes": up.index[-1].date().isoformat(), "forex": up.index[-1].date().isoformat()}
    assert sorted((h["market"], h["symbol"]) for h in store.run_hits(run_id)) == [("acoes", "UP"), ("forex", "EURUSD")]
    assert runner.status()["state"] == "done" and runner.status()["done"] == 4


def test_run_scan_only_uses_enabled_setups_of_the_requested_markets(monkeypatch):
    for s in store.list_setups():
        store.delete_setup(s["id"])
    store.create_setup("Só cripto", True, "alta", ["cripto"], DEF)
    store.create_setup("Desligado", False, "alta", ["acoes"], DEF)
    _patch_sources(monkeypatch, {"acoes": {"UP": ohlcv()}})
    run_id = runner.run_scan(["acoes"])
    assert store.run_hits(run_id) == [] and store.get_run(run_id)["setups"] == []


def test_run_scan_failure_is_recorded(monkeypatch):
    store.ensure_default_setups()

    def boom(m):
        raise RuntimeError("Binance fora do ar")

    monkeypatch.setattr(universe, "symbols_for", boom)
    run_id = runner.run_scan(["cripto"])
    assert store.get_run(run_id)["state"] == "error" and "Binance fora do ar" in store.get_run(run_id)["error"]
    assert runner.status()["state"] == "error"


def test_start_run_is_single_flight():
    runner._status["state"] = "running"
    assert runner.start_run(["acoes"]) is False
