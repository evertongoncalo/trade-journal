import pytest

from app import db
from app.alerts import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def make(symbol="BTCUSDT", price=100.0, direction="acima", **kw):
    return store.create("cripto", symbol, price, direction, **kw)


def test_create_and_read_back():
    a = make(note="rompimento", base_price=95.0)
    assert a["id"] == 1 and a["status"] == "ativo" and a["kind"] == "avulso"
    assert a["note"] == "rompimento" and a["base_price"] == 95.0 and a["distance_pct"] is None
    assert store.get(a["id"])["symbol"] == "BTCUSDT" and store.get(99) is None


def test_active_and_list_all_and_counts():
    a, b = make(), make(price=90, direction="abaixo")
    store.cancel(b["id"])
    assert [x["id"] for x in store.active()] == [a["id"]]
    assert [x["id"] for x in store.list_all()] == [b["id"], a["id"]]  # mais recente primeiro
    assert store.counts() == {"active": 1, "pending": 0}


def test_trigger_happens_once_and_creates_a_pending_response():
    a = make()
    assert store.mark_triggered(a["id"], "2026-01-05T15:01:00+00:00", 100.2) is True
    assert store.mark_triggered(a["id"], "2026-01-05T15:02:00+00:00", 101.0) is False
    got = store.get(a["id"])
    assert got["status"] == "disparado" and got["triggered_price"] == 100.2 and got["trigger_bar"].startswith("2026-01-05T15:01")
    assert store.counts() == {"active": 0, "pending": 1}
    assert store.cancel(a["id"]) is False  # disparado não vira cancelado


def test_respond_only_after_the_alert_fired():
    a = make()
    assert store.respond(a["id"], "ignorei") is False
    store.mark_triggered(a["id"], "2026-01-05T15:01:00+00:00", 100.2)
    assert store.respond(a["id"], "entrei", "entrei a mercado") is True
    got = store.get(a["id"])
    assert got["response"] == "entrei" and got["response_note"] == "entrei a mercado" and got["response_at"]
    assert store.counts()["pending"] == 0


def test_touch_records_progress_and_distance_to_the_level():
    a = make(price=110.0)
    store.touch(a["id"], "2026-01-05T15:05:00+00:00", 100.0)
    got = store.get(a["id"])
    assert got["checked_until"].startswith("2026-01-05T15:05") and got["last_price"] == 100.0
    assert got["distance_pct"] == pytest.approx(10.0)  # faltam 10% até o nível
    store.touch(a["id"], None, None)  # sem dado novo: mantém o que havia
    assert store.get(a["id"])["last_price"] == 100.0


def test_notify_result_is_stored():
    a = make()
    store.set_notified(a["id"], False, "x" * 500)
    got = store.get(a["id"])
    assert got["notify_ok"] is False and len(got["notify_detail"]) == 300 and got["notified_at"]


def test_cancel_for_entry_filters_by_kind_and_excludes_the_one_that_fired():
    entrada = make(price=95, kind="entrada", entry_id=7)
    inval = make(price=90, direction="abaixo", kind="invalidacao", entry_id=7)
    alvo = make(price=110, kind="alvo", entry_id=7)
    outro = make(price=50, kind="alvo", entry_id=8)
    avulso = make()
    n = store.cancel_for_entry(7, "plano tocou", kinds=("alvo", "invalidacao"), exclude_id=alvo["id"])
    assert n == 1
    assert store.get(inval["id"])["status"] == "cancelado" and store.get(inval["id"])["cancel_reason"] == "plano tocou"
    assert all(store.get(x["id"])["status"] == "ativo" for x in (entrada, alvo, outro, avulso))
    assert store.cancel_for_entry(7, "tese encerrada") == 2  # sem filtro: o que restava do registro 7


def test_delete():
    a = make()
    assert store.delete(a["id"]) is True and store.delete(a["id"]) is False
