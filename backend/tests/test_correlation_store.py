from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app import db
from app.correlation import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setitem(store._status, "state", "idle")


def ny_to_utc(ts: str) -> datetime:
    return pd.Timestamp(ts, tz="America/New_York").tz_convert("UTC").to_pydatetime()


def hourly(kind: str) -> pd.DataFrame:
    """Barras de 1h com Close = 100*dia + hora NY do início da barra."""
    rows = []
    for k, day in enumerate(pd.bdate_range("2026-01-05", "2026-01-12")):
        hours = [9.5 + i for i in range(7)] if kind == "equity" else range(24)
        for h in hours:
            start = pd.Timestamp(day.date(), tz="America/New_York") + pd.Timedelta(hours=h)
            rows.append((start.tz_convert("UTC"), 100.0 * k + h))
    s = pd.Series({t: v for t, v in rows})
    return pd.DataFrame({"Close": s})


def test_snap_picks_last_bar_that_closes_by_16h_ny_for_equities_and_24h_assets():
    now = ny_to_utc("2026-01-13 10:00")
    eq = store.snap_ny16(hourly("equity"), now=now)
    fx = store.snap_ny16(hourly("fx"), now=now)
    assert list(eq.values) == [100.0 * k + 15.5 for k in range(6)]  # barra de 15:30 (fecha às 16:00)
    assert list(fx.values) == [100.0 * k + 15 for k in range(6)]  # barra de 15:00 (fecha às 16:00)
    assert list(eq.index) == list(fx.index)


def test_snap_drops_the_day_in_progress_until_16h_ny():
    df = hourly("fx")
    last_day = pd.Timestamp("2026-01-12")
    before = store.snap_ny16(df, now=ny_to_utc("2026-01-12 10:00"))
    after = store.snap_ny16(df, now=ny_to_utc("2026-01-12 17:00"))
    assert last_day not in before.index
    assert last_day in after.index


def test_save_and_load_roundtrip():
    idx = pd.bdate_range("2026-01-05", periods=5)
    store.save_closes("AAA", pd.Series([1.0, 2, 3, 4, 5], index=idx))
    store.save_closes("BBB", pd.Series([4.0, 3, 2, 1], index=idx[1:]))
    wide = store.load_closes()
    assert list(wide.columns) == ["AAA", "BBB"]
    assert wide["AAA"].tolist() == [1, 2, 3, 4, 5]
    assert np.isnan(wide["BBB"].iloc[0])
    store.save_closes("AAA", pd.Series([9.0], index=idx[:1]))  # regravar substitui
    assert store.load_closes()["AAA"].dropna().tolist() == [9.0]


def test_universe_state_transitions():
    assert store.universe_state()["state"] == "vazio"
    idx = pd.bdate_range("2026-01-05", periods=3)
    expected = store.expected_symbols()
    for s in expected:
        store.save_closes(s, pd.Series([1.0, 2.0, 3.0], index=idx))
    st = store.universe_state()
    assert st["state"] == "ok" and st["symbols"] == st["expected"] == len(expected) and st["missing"] == []

    old = (datetime.now(timezone.utc) - timedelta(hours=store.STALE_HOURS + 1)).isoformat()
    with db.connect() as con:
        con.execute("UPDATE closes_meta SET updated_at = ? WHERE symbol = ?", (old, expected[0]))
    assert store.universe_state()["state"] == "desatualizado"


def test_refresh_universe_saves_downloads_and_reports_missing(monkeypatch):
    idx = pd.bdate_range("2026-01-05", periods=4)
    monkeypatch.setattr(
        store, "download_snaps", lambda syms, progress=None: {"AAA": pd.Series([1.0, 2, 3, 4], index=idx)}
    )
    store.refresh_universe(["AAA", "ZZZ"])
    st = store.status()
    assert st["state"] == "done" and st["missing"] == ["ZZZ"]
    assert "AAA" in store.load_closes().columns


def test_refresh_universe_reports_errors(monkeypatch):
    def boom(syms, progress=None):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(store, "download_snaps", boom)
    store.refresh_universe(["AAA"])
    assert store.status()["state"] == "error" and "sem rede" in store.status()["error"]


def test_start_refresh_is_single_flight(monkeypatch):
    store._status["state"] = "running"
    assert store.start_refresh(["AAA"]) is False
