import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.providers.base import ProviderError
from app import settings
from app.scanner import bars, data, engine, runner, store, universe
from app.scanner.defaults import DEFAULT_SETUPS, DEFAULT_SETUPS_H4
from app.scanner.conditions import CATALOG, normalize_definition

NY = "America/New_York"
COLS = ["Open", "High", "Low", "Close", "Volume"]


def hourly(starts, vol=100.0, base=100.0):
    """Barras de 1 hora cujos inícios são os horários dados (strings de Nova York)."""
    idx = pd.DatetimeIndex([pd.Timestamp(s, tz=NY) for s in starts]).tz_convert("UTC")
    close = base + np.arange(len(idx), dtype=float)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 1, "Low": close - 1, "Close": close, "Volume": vol}, index=idx)


def ny(s):
    return pd.Timestamp(s, tz=NY).tz_convert("UTC")


DAY_STOCK = [f"2026-10-20 {h}:30" for h in ("09", "10", "11", "12", "13", "14", "15")]


# ---------- grade de ações ----------


def test_stock_blocks_are_0930_and_1330_and_aggregate_ohlcv():
    df = hourly(DAY_STOCK)
    out = bars.h4_from_hourly(df, "acoes", now=ny("2026-10-20 17:00"))
    assert [i.tz_convert(NY).strftime("%H:%M") for i in out.index] == ["09:30", "13:30"]
    morning, afternoon = out.iloc[0], out.iloc[1]
    assert morning.Open == df.Open.iloc[0] and morning.Close == df.Close.iloc[3]
    assert morning.High == df.High.iloc[:4].max() and morning.Low == df.Low.iloc[:4].min()
    assert morning.Volume == 400 and afternoon.Volume == 300  # 4 horas e 3 horas
    assert afternoon.Open == df.Open.iloc[4] and afternoon.Close == df.Close.iloc[6]


def test_the_last_block_only_counts_after_it_ended():
    df = hourly(DAY_STOCK[:6])  # a barra das 15:30 ainda não existe
    # 13:29: a manhã ainda não terminou -> só o que veio antes (nada, aqui)
    assert bars.h4_from_hourly(df[df.index < ny("2026-10-20 13:30")], "acoes", now=ny("2026-10-20 13:29")).empty
    # 13:30 em diante: a manhã fechou
    out = bars.h4_from_hourly(df[df.index < ny("2026-10-20 13:30")], "acoes", now=ny("2026-10-20 13:31"))
    assert len(out) == 1 and out.index[0] == ny("2026-10-20 09:30")
    # tarde em andamento (relógio 15:00, faltam horas): fica de fora
    out = bars.h4_from_hourly(df, "acoes", now=ny("2026-10-20 15:00"))
    assert len(out) == 1


def test_a_block_without_its_last_hour_is_not_closed_even_if_the_clock_passed():
    """O Yahoo atrasa 10-15 min em alguns ativos: sem a última hora a barra nasceria incompleta."""
    morning_missing_last = hourly(DAY_STOCK[:3])  # 09:30, 10:30, 11:30 (falta a de 12:30)
    assert bars.h4_from_hourly(morning_missing_last, "acoes", now=ny("2026-10-20 13:35")).empty
    complete = hourly(DAY_STOCK[:4])
    assert len(bars.h4_from_hourly(complete, "acoes", now=ny("2026-10-20 13:35"))) == 1


def test_early_close_day_morning_block_still_closes():
    df = hourly([f"2026-11-27 {h}:30" for h in ("09", "10", "11", "12")])  # sexta depois do Dia de Ação de Graças
    out = bars.h4_from_hourly(df, "acoes", now=ny("2026-11-27 14:00"))
    assert len(out) == 1 and out.Volume.iloc[0] == 400


def test_block_end_for_stocks_and_others():
    assert bars.block_end("acoes", ny("2026-10-20 09:30")) == ny("2026-10-20 13:30")
    assert bars.block_end("acoes", ny("2026-10-20 13:30")) == ny("2026-10-20 16:00")  # a tarde tem 2h30
    assert bars.block_end("forex", ny("2026-10-20 05:00")) == ny("2026-10-20 09:00")
    start = pd.Timestamp("2026-10-20 12:00", tz="UTC")
    assert bars.block_end("cripto", start) == pd.Timestamp("2026-10-20 16:00", tz="UTC")


# ---------- grade de forex e ouro ----------


def test_forex_blocks_start_at_17_21_01_05_09_13_ny_in_summer_and_winter():
    for day, offset_h in (("2026-07-14", 4), ("2026-01-13", 5)):  # horário de verão e de inverno (UTC-4 / UTC-5)
        stamps = pd.date_range(f"{day} 00:00", periods=24, freq="h", tz=NY)
        df = hourly([str(t)[:16] for t in stamps])
        out = bars.h4_from_hourly(df, "forex", now=ny(f"{day} 23:59") + pd.Timedelta(days=1))
        hours = sorted({i.tz_convert(NY).hour for i in out.index})
        assert hours == [1, 5, 9, 13, 17, 21]
        # as 17:00 de Nova York são 21:00 UTC no verão e 22:00 no inverno: a grade acompanha o relógio de NY
        seventeen = next(i for i in out.index if i.tz_convert(NY).hour == 17)
        assert seventeen.hour == 17 + offset_h


def test_gold_break_leaves_a_three_hour_block_that_still_closes():
    # ouro: sem barra das 17:00 NY (pausa da bolsa); a barra das 17h-21h tem 18, 19 e 20
    df = hourly(["2026-10-20 13:00", "2026-10-20 14:00", "2026-10-20 15:00", "2026-10-20 16:00",
                 "2026-10-20 18:00", "2026-10-20 19:00", "2026-10-20 20:00"])
    out = bars.h4_from_hourly(df, "forex", now=ny("2026-10-20 21:05"))
    assert [i.tz_convert(NY).strftime("%H:%M") for i in out.index] == ["13:00", "17:00"]
    assert out.Volume.iloc[1] == 300


def test_weekend_gap_does_not_invent_bars():
    fri = [f"2026-10-23 {h:02d}:00" for h in range(9, 17)]  # sexta 09h-16h
    sun = [f"2026-10-25 {h:02d}:00" for h in range(17, 21)]  # domingo 17h-20h
    out = bars.h4_from_hourly(hourly(fri + sun), "forex", now=ny("2026-10-25 21:30"))
    assert [i.tz_convert(NY).strftime("%a %H:%M") for i in out.index] == ["Fri 09:00", "Fri 13:00", "Sun 17:00"]


def test_duplicates_and_unsorted_input_are_tolerated():
    df = hourly(DAY_STOCK)
    messy = pd.concat([df.iloc[::-1], df.iloc[:2]])
    out = bars.h4_from_hourly(messy, "acoes", now=ny("2026-10-20 17:00"))
    assert len(out) == 2 and out.Volume.tolist() == [400, 300]
    assert bars.h4_from_hourly(df.iloc[0:0], "acoes").empty


# ---------- engine em H4 ----------


def h4_frame(n=200, vol_morning=100.0, vol_afternoon=40.0, drift=0.002, seed=3):
    """Barras H4 de ações (duas por dia útil) com volume que depende do horário."""
    days = pd.bdate_range("2026-01-05", periods=n // 2)
    starts = []
    for d in days:
        starts += [pd.Timestamp(f"{d.date()} 09:30", tz=NY), pd.Timestamp(f"{d.date()} 13:30", tz=NY)]
    idx = pd.DatetimeIndex(starts).tz_convert("UTC")
    rng = np.random.default_rng(seed)
    close = 50 * np.exp(np.cumsum(rng.normal(drift, 0.006, len(idx))))
    vol = np.where(np.arange(len(idx)) % 2 == 0, vol_morning, vol_afternoon)
    return pd.DataFrame({"Open": close, "High": close * 1.003, "Low": close * 0.997, "Close": close, "Volume": vol}, index=idx)


def test_h4_volume_is_compared_with_the_same_time_of_day():
    df = h4_frame()
    plain = engine.features(df)["vol_ratio"]
    by_slot = engine.features(df, slot_tz=NY)["vol_ratio"]
    # o volume é sempre 100 de manhã e 40 à tarde: contra o mesmo horário, a razão é 1 em todas as barras
    assert by_slot.dropna().round(6).eq(1.0).all()
    assert plain.iloc[-2] > 1.4 and plain.iloc[-1] < 0.6  # sem isso a manhã pareceria "volume alto" todos os dias


def test_dollar_volume_per_day_sums_the_bars_of_each_day_and_skips_a_partial_today():
    df = h4_frame(n=60, vol_morning=100.0, vol_afternoon=40.0)
    full = engine.dollar_volume_per_day(df, "H4")
    # cada dia soma manhã + tarde (100 + 40) vezes o preço, não a média de uma barra só
    one_bar = float((df.Close * df.Volume).tail(20).mean())
    assert full > 1.5 * one_bar
    partial = engine.dollar_volume_per_day(df.iloc[:-1], "H4")  # hoje só tem a barra da manhã
    days = (df.Close * df.Volume).iloc[:-1].groupby(df.index[:-1].tz_convert(NY).date).sum()
    assert partial == pytest.approx(float(days.iloc[:-1].tail(20).mean()))


def test_liquidity_filter_in_h4_is_per_day_not_per_bar():
    df = h4_frame(n=80, vol_morning=300_000.0, vol_afternoon=300_000.0)  # ~US$ 15 mi por barra, ~30 mi por dia
    flt = {"min_price": 5, "min_dollar_volume": 20_000_000}
    assert float((df.Close * df.Volume).tail(20).mean()) < 20_000_000
    assert engine.passes_filters(df, "acoes", flt, "H4") is True
    assert engine.passes_filters(df, "acoes", flt, "D1") is False  # o mesmo quadro lido como diário


def setup_dict(timeframe, sid=1, markets=("acoes", "cripto", "forex")):
    d = normalize_definition({"required": [{"type": "trend_up", "params": {}}], "filters": {}})
    return {"id": sid, "name": f"s{sid}-{timeframe}", "direction": "alta", "markets": list(markets), "definition": d, "timeframe": timeframe}


def test_evaluate_symbol_only_runs_setups_of_the_frames_timeframe():
    df = h4_frame(drift=0.004)
    both = [setup_dict("D1", 1), setup_dict("H4", 2)]
    h4_hits = engine.evaluate_symbol("acoes", "AAA", df, both, "H4")
    assert [h["setup_id"] for h in h4_hits] == [2] and h4_hits[0]["timeframe"] == "H4"
    d = h4_hits[0]["details"]
    assert d["timeframe"] == "H4" and d["as_of"] == df.index[-1].isoformat()
    assert pd.Timestamp(d["as_of_end"]) == bars.block_end("acoes", df.index[-1])
    d1_hits = engine.evaluate_symbol("acoes", "AAA", df, both)  # padrão: D1
    assert [h["setup_id"] for h in d1_hits] == [1] and d1_hits[0]["details"]["as_of_end"] is None


def test_setups_without_a_timeframe_key_are_daily():
    legacy = setup_dict("D1")
    legacy.pop("timeframe")
    assert engine.evaluate_symbol("acoes", "AAA", h4_frame(drift=0.004), [legacy], "H4") == []


def test_volume_condition_wording_changes_in_h4():
    spec = CATALOG["volume_ratio_above"]
    assert spec.render({"x": 1.2}) == "Volume > 1.2× a média de 20 barras"
    assert "mesmo horário" in spec.render({"x": 1.2}, "H4")
    assert CATALOG["rsi_rising"].render({}, "H4") == CATALOG["rsi_rising"].render({})  # sem texto próprio: igual


# ---------- dados ----------


def test_clean_h4_builds_bars_and_requires_enough_history():
    days = pd.bdate_range("2026-06-01", periods=45)
    starts = [f"{d.date()} {h}:30" for d in days for h in ("09", "10", "11", "12", "13", "14", "15")]
    df = hourly(starts)
    df.index = df.index.tz_convert(NY)  # o yfinance devolve o fuso do pregão
    out = data._clean_h4(df, "acoes", ny("2026-08-06 17:00"))
    assert out is not None and out.index.tz is not None and len(out) == 90  # 45 dias x 2
    assert data._clean_h4(df.iloc[:100], "acoes", ny("2026-08-06 17:00")) is None  # 100 horas -> ~28 barras < 60


def test_klines_frame_drops_the_bar_in_progress_and_short_history():
    now_ms = 1_800_000_000_000
    four = 4 * 3_600_000
    rows = []
    for k in range(70):
        open_t = now_ms - (70 - k) * four + 1_000_000  # a última abre antes do limite mas fecha no futuro
        rows.append([open_t, "1", "2", "0.5", "1.5", "10", open_t + four - 1, "0", 0, "0", "0", "0"])
    df = data._klines_frame(rows, now_ms)
    assert len(df) == 69 and df.index.tz is not None
    with pytest.raises(ProviderError):
        data._klines_frame([], now_ms)
    with pytest.raises(ProviderError):
        data._klines_frame(rows[:20], now_ms)


def test_binance_h4_asks_for_4h_klines(monkeypatch):
    seen = []
    monkeypatch.setattr(data, "binance_get", lambda path, params: seen.append(params) or [])
    with pytest.raises(ProviderError):
        data._binance_h4_one("BTCUSDT", 1)
    assert seen[0]["interval"] == "4h" and seen[0]["limit"] == data.H4_BINANCE_LIMIT


def test_yahoo_h4_asks_for_hourly_data_and_daily_keeps_its_own(monkeypatch):
    calls = []

    def fake_download(syms, **kw):
        calls.append((kw["period"], kw["interval"]))
        return pd.DataFrame()

    class NoTicker:
        def __init__(self, sym):
            pass

        def history(self, **kw):
            raise RuntimeError("sem rede")

    monkeypatch.setattr(data.yf, "download", fake_download)
    monkeypatch.setattr(data.yf, "Ticker", NoTicker)
    frames, errors = data.fetch_yahoo_h4([("AAA", "AAA")], "acoes", None)
    assert frames == {} and errors == {"AAA": "sem dados suficientes no Yahoo"}
    data.fetch_yahoo_daily([("AAA", "AAA")], pd.Timestamp("2026-01-01", tz="UTC"))
    assert calls == [("1y", "1h"), ("2y", "1d")]


def test_fetch_dispatches_by_timeframe_and_market(monkeypatch):
    seen = []
    monkeypatch.setattr(data, "fetch_daily", lambda m, syms, progress=None, now=None: seen.append(("D1", m)) or ({}, {}))
    monkeypatch.setattr(data, "fetch_binance_h4", lambda syms, progress=None: seen.append(("H4", "binance", syms)) or ({}, {}))
    monkeypatch.setattr(
        data, "fetch_yahoo_h4", lambda pairs, market, now, progress=None: seen.append(("H4", market, pairs)) or ({}, {})
    )
    data.fetch("acoes", "D1", ["AAA"])
    data.fetch("cripto", "H4", ["BTCUSDT"])
    data.fetch("forex", "H4", ["XAUUSD"])
    assert seen == [("D1", "acoes"), ("H4", "binance", ["BTCUSDT"]), ("H4", "forex", [("XAUUSD", "GC=F")])]


# ---------- banco e API ----------


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setitem(runner._status, "state", "idle")
    db.init_db()
    return tmp_path / "t.db"


DEF = {"required": [{"type": "trend_up", "params": {}}], "confirmations": [], "min_confirmations": 0}


def test_setup_timeframe_is_stored_updated_and_validated(tmp_db):
    s = store.create_setup("Diário", True, "alta", ["acoes"], DEF)
    assert s["timeframe"] == "D1"
    h = store.create_setup("Quatro horas", True, "alta", ["acoes"], DEF, "H4")
    assert h["timeframe"] == "H4"
    assert store.update_setup(s["id"], "Diário", True, "alta", ["acoes"], DEF, "H4")["timeframe"] == "H4"
    with pytest.raises(ValueError):
        store.create_setup("Ruim", True, "alta", ["acoes"], DEF, "H1")
    with pytest.raises(ValueError):
        store.update_setup(s["id"], "Ruim", True, "alta", ["acoes"], DEF, "W1")


def test_old_database_gets_the_timeframe_columns_and_keeps_its_rows(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE setups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            direction TEXT NOT NULL, markets TEXT NOT NULL, definition_json TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE scan_hits (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, setup_id INTEGER,
            setup_name TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL, direction TEXT NOT NULL, price REAL,
            details_json TEXT NOT NULL, opened_at TEXT);
        INSERT INTO setups (name, direction, markets, definition_json, created_at, updated_at)
            VALUES ('Antigo', 'alta', '["acoes"]', '{}', 'x', 'x');
        INSERT INTO scan_hits (run_id, setup_name, market, symbol, direction, price, details_json)
            VALUES (1, 'Antigo', 'acoes', 'AAA', 'alta', 10, '{}');
        """
    )
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    db.init_db()  # rodar de novo não pode falhar nem duplicar a coluna
    with db.connect() as c:
        assert c.execute("SELECT timeframe FROM setups").fetchone()[0] == "D1"
        assert c.execute("SELECT timeframe FROM scan_hits").fetchone()[0] == "D1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setitem(runner._status, "state", "idle")
    with TestClient(app) as c:
        yield c


SETUP_BODY = {
    "name": "Pullback H4", "enabled": True, "direction": "alta", "markets": ["acoes"], "timeframe": "H4",
    "definition": {"required": [{"type": "rsi_between", "params": {"lo": 40, "hi": 60}}], "confirmations": [],
                   "min_confirmations": 0, "filters": {"min_price": 5, "min_dollar_volume": 0}},
}


def test_api_setup_timeframe_roundtrip(client):
    initial = client.get("/api/scanner/setups").json()
    assert sorted(s["timeframe"] for s in initial) == ["D1"] * 3 + ["H4"] * 3  # os três iniciais, nos dois timeframes
    created = client.post("/api/scanner/setups", json=SETUP_BODY)
    assert created.status_code == 201 and created.json()["timeframe"] == "H4"
    sid = created.json()["id"]
    assert client.put(f"/api/scanner/setups/{sid}", json={**SETUP_BODY, "timeframe": "D1"}).json()["timeframe"] == "D1"
    no_tf = {k: v for k, v in SETUP_BODY.items() if k != "timeframe"}
    assert client.post("/api/scanner/setups", json=no_tf).json()["timeframe"] == "D1"  # padrão
    assert client.post("/api/scanner/setups", json={**SETUP_BODY, "timeframe": "H1"}).status_code == 422


# ---------- varredura ----------


def _ohlcv(n=300, drift=0.003, seed=1):
    rng = np.random.default_rng(seed)
    close = 50 * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"Open": close, "High": close * 1.004, "Low": close * 0.996, "Close": close, "Volume": 5e6}, index=idx)


def _clear(tmp_db):
    for s in store.list_setups():
        store.delete_setup(s["id"])


def test_run_scan_fetches_only_the_timeframes_that_setups_use(tmp_db, monkeypatch):
    _clear(tmp_db)
    store.create_setup("Só H4 ações", True, "alta", ["acoes"], DEF, "H4")
    store.create_setup("D1 cripto", True, "alta", ["cripto"], DEF, "D1")
    calls = []
    up = h4_frame(drift=0.004)
    daily = _ohlcv()
    monkeypatch.setattr(universe, "symbols_for", lambda m: {"acoes": ["UP", "BAD"], "cripto": ["BTCUSDT"], "forex": ["EURUSD"]}[m])

    def fetch_daily(m, syms, progress=None, now=None):
        calls.append(("D1", m))
        progress and progress(len(syms))
        return {s: daily for s in syms}, {}

    def fetch_h4(m, syms, progress=None, now=None):
        calls.append(("H4", m))
        progress and progress(len(syms))
        return {"UP": up}, {"BAD": "sem dados suficientes no Yahoo"}

    monkeypatch.setattr(data, "fetch_daily", fetch_daily)
    monkeypatch.setattr(data, "fetch_h4", fetch_h4)
    run_id = runner.run_scan(["acoes", "cripto", "forex"])  # forex não tem setup: nem é baixado
    assert calls == [("H4", "acoes"), ("D1", "cripto")]
    run = store.get_run(run_id)
    assert run["state"] == "done" and run["symbols_total"] == 3 and run["symbols_ok"] == 2  # UP e BTCUSDT
    assert run["errors"] == {"acoes:BAD (H4)": "sem dados suficientes no Yahoo"}
    assert run["as_of"] == {"acoes:H4": up.index[-1].isoformat(), "cripto": daily.index[-1].date().isoformat()}
    assert runner.status()["total"] == 3 and runner.status()["done"] == 3
    hits = store.run_hits(run_id)
    assert sorted((h["market"], h["symbol"], h["timeframe"]) for h in hits) == [("acoes", "UP", "H4"), ("cripto", "BTCUSDT", "D1")]
    h4_hit = next(h for h in hits if h["timeframe"] == "H4")
    assert h4_hit["details"]["as_of_end"] and h4_hit["details"]["timeframe"] == "H4"


def test_run_scan_with_both_timeframes_marks_an_asset_ok_only_if_both_worked(tmp_db, monkeypatch):
    _clear(tmp_db)
    store.create_setup("D1", True, "alta", ["forex"], DEF, "D1")
    store.create_setup("H4", True, "alta", ["forex"], DEF, "H4")
    monkeypatch.setattr(universe, "symbols_for", lambda m: ["EURUSD", "GBPUSD"])
    daily = _ohlcv()
    monkeypatch.setattr(data, "fetch_daily", lambda m, syms, progress=None, now=None: ((progress and progress(len(syms))) or ({s: daily for s in syms}, {})))
    monkeypatch.setattr(
        data, "fetch_h4",
        lambda m, syms, progress=None, now=None: ((progress and progress(len(syms))) or ({"EURUSD": h4_frame()}, {"GBPUSD": "x"})),
    )
    run = store.get_run(runner.run_scan(["forex"]))
    assert run["symbols_total"] == 2 and run["symbols_ok"] == 1  # GBPUSD falhou em H4
    assert run["errors_count"] == 1 and "forex:GBPUSD (H4)" in run["errors"]
    assert runner.status()["total"] == 4 and runner.status()["done"] == 4  # 2 ativos x 2 timeframes


# ---------- setups iniciais também em H4 ----------


def _wipe():
    for s in store.list_setups():
        store.delete_setup(s["id"])


def _d1_defaults_only():
    """Um banco como o de antes da v0.7: só os três diários, sem a marca de que as versões H4 foram criadas."""
    _wipe()
    settings.delete(store.H4_DEFAULTS_FLAG)
    for s in DEFAULT_SETUPS:
        store._create_default(s)


def test_a_new_database_gets_each_default_in_d1_and_h4_with_the_same_rules(tmp_db):
    _wipe()
    settings.delete(store.H4_DEFAULTS_FLAG)
    store.ensure_default_setups()
    store.ensure_default_setups()  # não duplica
    by_name = {s["name"]: s for s in store.list_setups()}
    assert len(by_name) == 6
    for d1 in DEFAULT_SETUPS:
        h4 = by_name[d1["name"] + " (H4)"]
        orig = by_name[d1["name"]]
        assert (orig["timeframe"], h4["timeframe"]) == ("D1", "H4")
        assert h4["enabled"] and h4["direction"] == orig["direction"] and h4["markets"] == orig["markets"]
        assert h4["definition"] == orig["definition"]  # mesmas condições e filtros; só muda o timeframe


def test_an_existing_database_gets_the_h4_versions_once_and_never_again(tmp_db):
    _d1_defaults_only()
    custom = store.create_setup("Meu setup", True, "alta", ["acoes"], DEF)
    store.ensure_default_setups()
    names = {s["name"] for s in store.list_setups()}
    assert names == {*(s["name"] for s in DEFAULT_SETUPS), *(s["name"] for s in DEFAULT_SETUPS_H4), "Meu setup"}
    assert store.get_setup(custom["id"])["timeframe"] == "D1"  # o que é seu não muda

    gone = next(s for s in store.list_setups() if s["name"] == "Momentum em zona neutra (H4)")
    store.delete_setup(gone["id"])  # você apaga um H4 de propósito...
    store.ensure_default_setups()
    store.ensure_default_setups()
    assert "Momentum em zona neutra (H4)" not in {s["name"] for s in store.list_setups()}  # ...e ele não volta


def test_only_defaults_that_still_exist_get_an_h4_copy_and_the_copy_uses_the_original_rules(tmp_db):
    _d1_defaults_only()
    momentum = next(s for s in store.list_setups() if s["name"] == "Momentum em zona neutra")
    store.delete_setup(momentum["id"])  # você tinha apagado esse D1: não faz sentido ganhar o H4
    pullback = next(s for s in store.list_setups() if s["name"] == "Pullback em tendência de alta")
    edited = {**pullback["definition"], "required": [{"type": "trend_up", "params": {}}]}
    store.update_setup(pullback["id"], pullback["name"], True, "alta", pullback["markets"], edited)  # você editou este
    renamed = next(s for s in store.list_setups() if s["name"] == "Recuperação de sobrevenda")
    store.update_setup(renamed["id"], "Meu rebote", True, "alta", renamed["markets"], renamed["definition"])  # e renomeou este
    store.ensure_default_setups()
    by_name = {s["name"]: s for s in store.list_setups()}
    assert "Momentum em zona neutra (H4)" not in by_name and "Recuperação de sobrevenda (H4)" not in by_name
    h4 = by_name["Pullback em tendência de alta (H4)"]
    original = next(s for s in DEFAULT_SETUPS if s["name"] == "Pullback em tendência de alta")
    assert h4["definition"]["required"] == normalize_definition(original["definition"])["required"]  # as regras originais
    assert by_name["Pullback em tendência de alta"]["definition"]["required"] == edited["required"]  # o D1 editado segue seu


def test_the_default_h4_setups_are_independent_copies_of_the_d1_ones():
    for d1, h4 in zip(DEFAULT_SETUPS, DEFAULT_SETUPS_H4):
        assert h4["name"] == d1["name"] + " (H4)" and h4["timeframe"] == "H4"
        assert h4["definition"] == d1["definition"] and h4["definition"] is not d1["definition"]
        assert h4["definition"]["required"] is not d1["definition"]["required"]
