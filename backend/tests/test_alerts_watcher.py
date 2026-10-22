import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app import db
from app.alerts import store, watcher

T0 = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(minutes=10)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def bars(rows, start=T0):
    idx = pd.date_range(start, periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame(
        [(c, h, lo, c, 0.0) for h, lo, c in rows], columns=["Open", "High", "Low", "Close", "Volume"], index=idx
    )


def backdate(alert_id, when):
    with db.connect() as con:
        con.execute("UPDATE alerts SET created_at = ? WHERE id = ?", (when.isoformat(), alert_id))


def make(symbol="BTCUSDT", price=100.0, direction="acima", market="cripto", **kw):
    a = store.create(market, symbol, price, direction, **kw)
    backdate(a["id"], T0 - timedelta(seconds=30))
    return a


class Recorder:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, title, body, url):
        self.calls.append((title, body, url))
        return self.ok, "enviada" if self.ok else "sem permissão"


def fetch_returning(table, calls=None):
    def fetch(market, symbol, since, now):
        if calls is not None:
            calls.append((market, symbol, since))
        value = table[(market, symbol)]
        if isinstance(value, Exception):
            raise value
        return value, "1m"

    return fetch


WICK = bars([(99.0, 98.0, 98.5), (100.4, 98.5, 99.0), (99.5, 98.8, 99.2)])
QUIET = bars([(99.0, 98.0, 98.5), (99.2, 98.4, 98.9)])


def test_fires_on_a_wick_notifies_once_and_never_again():
    a = make()
    rec = Recorder()
    fired = watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): WICK}), rec)
    assert [x["id"] for x in fired] == [a["id"]]
    got = store.get(a["id"])
    assert got["status"] == "disparado" and got["triggered_price"] == 100.4 and got["notify_ok"] is True
    assert len(rec.calls) == 1
    title, body, url = rec.calls[0]
    assert "BTCUSDT subiu até 100" in title and "Máxima de 100.4" in body and url.startswith("http")

    assert watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): WICK}), rec) == []
    assert len(rec.calls) == 1


def test_down_alert_uses_the_low_and_says_fell():
    make(price=98.3, direction="abaixo")
    rec = Recorder()
    watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): QUIET}), rec)
    title, body, _ = rec.calls[0]
    assert "caiu até 98.3" in title and "Mínima de 98" in body


def test_quiet_market_only_records_progress():
    a = make()
    rec = Recorder()
    assert watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): QUIET}), rec) == []
    got = store.get(a["id"])
    assert got["status"] == "ativo" and got["last_price"] == 98.9 and got["checked_until"].startswith("2026-01-05T15:01")
    assert rec.calls == []


def test_notification_failure_is_recorded_but_the_alert_still_fires():
    a = make()
    watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): WICK}), Recorder(ok=False))
    got = store.get(a["id"])
    assert got["status"] == "disparado" and got["notify_ok"] is False and got["notify_detail"] == "sem permissão"


def test_one_fetch_per_symbol_even_with_several_alerts():
    make(price=100.0)
    make(price=99.5)
    make(symbol="ETHUSDT", price=100.0)
    calls = []
    table = {("cripto", "BTCUSDT"): QUIET, ("cripto", "ETHUSDT"): QUIET}
    watcher.check_once(NOW, fetch_returning(table, calls), Recorder())
    assert sorted(c[1] for c in calls) == ["BTCUSDT", "ETHUSDT"]


def test_fetch_window_starts_at_the_earliest_unchecked_moment():
    a, b = make(), make(price=99.9)
    store.touch(b["id"], (T0 + timedelta(minutes=5)).isoformat(), 98.0)
    # `a` ainda não foi verificado (começa na 1ª barra depois da criação, 15:00); `b` já foi até 15:05
    assert store.get(a["id"])["checked_until"] is None
    calls = []
    watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): QUIET}, calls), Recorder())
    assert calls[0][2] == T0  # a janela começa no mais antigo dos dois
    assert store.get(a["id"])["checked_until"] is not None  # e depois do ciclo `a` também tem progresso registrado


def test_a_failing_symbol_does_not_block_the_others():
    bad = make(symbol="BADUSDT")
    good = make()
    table = {("cripto", "BADUSDT"): RuntimeError("Binance fora do ar"), ("cripto", "BTCUSDT"): WICK}
    fired = watcher.check_once(NOW, fetch_returning(table), Recorder())
    assert [x["id"] for x in fired] == [good["id"]]
    assert store.get(bad["id"])["status"] == "ativo"
    st = watcher.status()
    assert st["errors"] == {"cripto:BADUSDT": "Binance fora do ar"} and st["last_error"] == "Binance fora do ar"
    assert st["last_cycle_at"] == NOW.isoformat()


def test_plan_target_hit_cancels_the_invalidation_but_keeps_the_entry_alert():
    entrada = make(price=95, direction="abaixo", kind="entrada", entry_id=3)
    inval = make(price=90, direction="abaixo", kind="invalidacao", entry_id=3)
    alvo = make(price=100, kind="alvo", entry_id=3)
    watcher.check_once(NOW, fetch_returning({("cripto", "BTCUSDT"): WICK}), Recorder())
    assert store.get(alvo["id"])["status"] == "disparado"
    assert store.get(inval["id"])["status"] == "cancelado"
    assert "alvo" in store.get(inval["id"])["cancel_reason"]
    assert store.get(entrada["id"])["status"] == "ativo"


def test_toast_text():
    alert = {"symbol": "EURUSD", "direction": "abaixo", "price": 1.12, "note": "Plano #4: Invalidação"}
    title, body = watcher.toast_text(alert, {"bar": T0, "extreme": 1.1195})
    assert title == "EURUSD caiu até 1.12"
    assert body.startswith("Mínima de 1.1195 na barra de ") and body.endswith("Plano #4: Invalidação")


def test_background_loop_runs_cycles_and_stops(monkeypatch):
    ran = threading.Event()
    counter = {"n": 0}

    def fake_check():
        counter["n"] += 1
        if counter["n"] >= 2:
            ran.set()
        return []

    monkeypatch.setattr(watcher, "check_once", fake_check)
    monkeypatch.setattr(watcher, "FIRST_CYCLE_DELAY", 0.0)
    assert watcher.start(interval=0.05) is True
    try:
        assert watcher.start(interval=0.05) is False  # já está ligada
        assert ran.wait(3), "a vigilância não rodou dois ciclos"
        assert watcher.status()["running"] is True
    finally:
        watcher.stop()
    assert watcher.status()["running"] is False
    n = counter["n"]
    time.sleep(0.2)
    assert counter["n"] == n  # parou de verdade


def test_loop_survives_an_exception_in_a_cycle(monkeypatch):
    done = threading.Event()
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("rede caiu")
        done.set()
        return []

    monkeypatch.setattr(watcher, "check_once", flaky)
    monkeypatch.setattr(watcher, "FIRST_CYCLE_DELAY", 0.0)
    watcher.start(interval=0.05)
    try:
        assert done.wait(3)
        assert watcher.status()["last_error"] == "rede caiu"
    finally:
        watcher.stop()
