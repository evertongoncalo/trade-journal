from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import db
from app.alerts import notify, service, store, watcher
from app.main import app
from app.providers import registry
from app.providers.base import PriceHistory, ProviderError

CURRENT = 100.0


def fake_fetch(market, symbol, interval, days):
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("h"), periods=5, freq="h")
    df = pd.DataFrame({c: CURRENT for c in ["Open", "High", "Low", "Close", "Volume"]}, index=idx)
    return PriceHistory(df, "fake", symbol, interval)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(registry, "fetch", fake_fetch)
    with TestClient(app) as c:
        yield c


def alert_body(**kw):
    return {"market": "acoes", "symbol": "nvda", "price": 110, "direction": "acima", "note": "rompimento", **kw}


def plan_body(**kw):
    return {
        "market": "acoes", "symbol": "nvda", "decision": "entrei", "direction": "alta", "entry_price": 100,
        "invalidation": 95, "target": 110, "horizon_days": 5, "thesis": "teste", **kw,
    }


# ---------- regras de criação ----------


def test_plan_specs_for_long_and_short():
    entry = {"decision": "entrei", "direction": "alta", "entry_price": 100, "invalidation": 95, "target": 110}
    assert service.plan_specs(entry, None) == [("invalidacao", 95, "abaixo"), ("alvo", 110, "acima")]
    short = {**entry, "direction": "baixa", "invalidation": 105, "target": 90}
    assert service.plan_specs(short, None) == [("invalidacao", 105, "acima"), ("alvo", 90, "abaixo")]


def test_plan_specs_entry_alert_only_when_watching_and_away_from_price():
    entry = {"decision": "observando", "direction": "alta", "entry_price": 100, "invalidation": 95, "target": 110}
    assert service.plan_specs(entry, 90)[0] == ("entrada", 100, "acima")  # espera subir até a entrada
    assert service.plan_specs(entry, 108)[0] == ("entrada", 100, "abaixo")  # espera um recuo
    assert [s[0] for s in service.plan_specs(entry, 100.05)] == ["invalidacao", "alvo"]  # já está na entrada
    assert [s[0] for s in service.plan_specs(entry, None)] == ["invalidacao", "alvo"]
    assert service.plan_specs({**entry, "decision": "entrei"}, 90)[0][0] == "invalidacao"
    assert service.plan_specs({**entry, "decision": "nao_entrei"}, 90) == []


# ---------- alerta avulso pela API ----------


def test_create_manual_alert_and_list(client):
    r = client.post("/api/alerts", json=alert_body())
    assert r.status_code == 201
    body = r.json()
    assert body["symbol"] == "NVDA" and body["status"] == "ativo" and body["kind"] == "avulso"
    assert body["base_price"] == CURRENT and body["note"] == "rompimento"
    assert [a["id"] for a in client.get("/api/alerts").json()] == [body["id"]]


def test_direction_must_match_the_current_price(client):
    r = client.post("/api/alerts", json=alert_body(price=90, direction="acima"))
    assert r.status_code == 422 and "abaixo" in r.json()["detail"]
    r = client.post("/api/alerts", json=alert_body(price=110, direction="abaixo"))
    assert r.status_code == 422 and "acima" in r.json()["detail"]
    assert client.post("/api/alerts", json=alert_body(price=90, direction="abaixo")).status_code == 201


@pytest.mark.parametrize(
    "patch",
    [{"price": 0}, {"price": -5}, {"direction": "lado"}, {"market": "bolsa"}, {"symbol": ""}, {"note": "x" * 201}],
)
def test_invalid_alert_payloads_are_rejected(client, patch):
    assert client.post("/api/alerts", json=alert_body(**patch)).status_code == 422


def test_forex_symbol_format_and_provider_failure(client, monkeypatch):
    assert client.post("/api/alerts", json=alert_body(market="forex", symbol="EUR")).status_code == 422

    def boom(*a, **k):
        raise ProviderError("sem dados")

    monkeypatch.setattr(registry, "fetch", boom)
    assert client.post("/api/alerts", json=alert_body()).status_code == 502


def test_cancel_respond_and_delete(client):
    a = client.post("/api/alerts", json=alert_body()).json()
    assert client.post(f"/api/alerts/{a['id']}/respond", json={"response": "entrei"}).status_code == 404  # ainda não disparou

    store.mark_triggered(a["id"], "2026-01-05T15:01:00+00:00", 110.2)
    r = client.post(f"/api/alerts/{a['id']}/respond", json={"response": "ignorei", "note": "tarde demais"})
    assert r.status_code == 200 and r.json()["response"] == "ignorei" and r.json()["response_note"] == "tarde demais"
    assert client.post(f"/api/alerts/{a['id']}/respond", json={"response": "talvez"}).status_code == 422
    assert client.post(f"/api/alerts/{a['id']}/cancel").status_code == 404  # disparado não cancela

    b = client.post("/api/alerts", json=alert_body(price=120)).json()
    assert client.post(f"/api/alerts/{b['id']}/cancel").json()["status"] == "cancelado"
    assert client.delete(f"/api/alerts/{b['id']}").status_code == 204
    assert client.delete(f"/api/alerts/{b['id']}").status_code == 404


def test_status_check_and_notification_test_endpoints(client, monkeypatch):
    client.post("/api/alerts", json=alert_body())
    monkeypatch.setattr(notify, "available", lambda: (True, "ok"))
    st = client.get("/api/alerts/status").json()
    assert st["active"] == 1 and st["pending"] == 0
    assert st["notifications"] == {"available": True, "detail": "ok"} and "running" in st["watcher"]

    monkeypatch.setattr(watcher, "check_once", lambda *a, **k: [{"id": 1}])
    assert client.post("/api/alerts/check").json()["fired"] == [{"id": 1}]

    sent = []
    monkeypatch.setattr(notify, "send", lambda t, b, u=None: sent.append((t, b, u)) or (True, "enviada"))
    assert client.post("/api/alerts/test-notification").json() == {"ok": True, "detail": "enviada"}
    assert sent and "teste" in sent[0][0].lower()


# ---------- integração com o diário ----------


def test_journal_entry_creates_alerts_for_its_plan_levels(client):
    entry = client.post("/api/journal", json=plan_body()).json()
    assert [(a["kind"], a["direction"], a["price"]) for a in entry["alerts"]] == [
        ("invalidacao", "abaixo", 95), ("alvo", "acima", 110)
    ]
    listed = {a["kind"]: a for a in client.get("/api/alerts").json()}
    assert listed["alvo"]["entry_id"] == entry["id"] and f"Plano #{entry['id']}" in listed["alvo"]["note"]


def test_watching_entry_gets_an_entry_alert_and_skipped_entry_gets_none(client, monkeypatch):
    monkeypatch.setattr(service, "current_price", lambda m, s: 90.0)
    watching = client.post("/api/journal", json=plan_body(decision="observando")).json()
    assert [a["kind"] for a in watching["alerts"]] == ["entrada", "invalidacao", "alvo"]
    assert watching["alerts"][0]["direction"] == "acima"
    skipped = client.post("/api/journal", json=plan_body(decision="nao_entrei")).json()
    assert skipped["alerts"] == []


def test_a_failure_creating_alerts_does_not_block_the_journal(client, monkeypatch):
    def boom(entry):
        raise RuntimeError("falha")

    monkeypatch.setattr(service, "create_plan_alerts", boom)
    r = client.post("/api/journal", json=plan_body())
    assert r.status_code == 201 and r.json()["alerts"] == []


def active_kinds(client, entry_id):
    return [a["kind"] for a in client.get("/api/alerts").json() if a["entry_id"] == entry_id and a["status"] == "ativo"]


def test_early_exit_and_delete_cancel_the_plan_alerts(client):
    a = client.post("/api/journal", json=plan_body()).json()
    assert active_kinds(client, a["id"]) == ["alvo", "invalidacao"]
    client.post(f"/api/journal/{a['id']}/early-exit", json={"price": 97})
    assert active_kinds(client, a["id"]) == []

    b = client.post("/api/journal", json=plan_body()).json()
    client.delete(f"/api/journal/{b['id']}")
    assert active_kinds(client, b["id"]) == []


def test_closing_the_thesis_cancels_the_plan_alerts(client, monkeypatch):
    entry = client.post("/api/journal", json=plan_body()).json()
    own = client.post("/api/alerts", json=alert_body(price=120)).json()  # avulso: não pertence ao plano

    def hits_target(market, symbol, interval, days):
        idx = pd.date_range(datetime.now(timezone.utc) + timedelta(hours=1), periods=2, freq="h")
        df = pd.DataFrame(
            [(100, 102, 99, 101), (101, 111, 100, 110)], columns=["Open", "High", "Low", "Close"], index=idx
        ).assign(Volume=0.0)
        return PriceHistory(df, "fake", symbol, interval)

    monkeypatch.setattr(registry, "fetch", hits_target)
    assert client.post("/api/journal/refresh").json()["encerradas"] == 1
    assert active_kinds(client, entry["id"]) == []
    reasons = {a["cancel_reason"] for a in client.get("/api/alerts").json() if a["entry_id"] == entry["id"]}
    assert reasons == {"tese encerrada: alvo"}
    assert next(a for a in client.get("/api/alerts").json() if a["id"] == own["id"])["status"] == "ativo"
