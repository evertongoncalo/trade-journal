import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.scanner import runner, store

SETUP = {
    "name": "Teste",
    "enabled": True,
    "direction": "alta",
    "markets": ["acoes"],
    "definition": {
        "required": [{"type": "rsi_between", "params": {"lo": 40, "hi": 60}}],
        "confirmations": [{"type": "macd_above_signal", "params": {}}],
        "min_confirmations": 1,
        "filters": {"min_price": 5, "min_dollar_volume": 1_000_000},
    },
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setitem(runner._status, "state", "idle")
    with TestClient(app) as c:  # o startup cria os setups iniciais
        yield c


def test_catalog_lists_conditions_with_params(client):
    cat = client.get("/api/scanner/catalog").json()
    rsi = next(c for c in cat if c["id"] == "rsi_between")
    assert [p["name"] for p in rsi["params"]] == ["lo", "hi"]
    assert next(c for c in cat if c["id"] == "volume_ratio_above")["needs_volume"] is True


def test_default_setups_exist_after_startup(client):
    names = [s["name"] for s in client.get("/api/scanner/setups").json()]
    assert "Pullback em tendência de alta" in names and "Pullback em tendência de alta (H4)" in names and len(names) == 6


def test_setup_crud(client):
    created = client.post("/api/scanner/setups", json=SETUP)
    assert created.status_code == 201
    sid = created.json()["id"]
    assert created.json()["definition"]["filters"]["min_price"] == 5

    changed = {**SETUP, "name": "Outro", "enabled": False}
    r = client.put(f"/api/scanner/setups/{sid}", json=changed)
    assert r.status_code == 200 and r.json()["name"] == "Outro" and r.json()["enabled"] is False
    assert client.put("/api/scanner/setups/9999", json=SETUP).status_code == 404

    assert client.delete(f"/api/scanner/setups/{sid}").status_code == 204
    assert client.delete(f"/api/scanner/setups/{sid}").status_code == 404


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["definition"]["required"].append({"type": "nao_existe"}),
        lambda s: s["definition"].update(required=[], confirmations=[], min_confirmations=0),
        lambda s: s["definition"].update(min_confirmations=5),
        lambda s: s["definition"]["required"][0]["params"].update(lo=-10),
        lambda s: s.update(markets=[]),
        lambda s: s.update(name=""),
        lambda s: s.update(direction="lateral"),
    ],
)
def test_setup_validation_errors(client, mutate):
    import copy

    body = copy.deepcopy(SETUP)
    mutate(body)
    assert client.post("/api/scanner/setups", json=body).status_code == 422


def test_run_requires_an_enabled_setup_for_the_markets(client):
    for s in client.get("/api/scanner/setups").json():
        client.delete(f"/api/scanner/setups/{s['id']}")
    assert client.post("/api/scanner/run", json={}).status_code == 400


def test_run_starts_in_background_and_reports_status(client, monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "start_run", lambda markets: seen.append(markets) or True)
    r = client.post("/api/scanner/run", json={"markets": ["forex"]})
    assert r.status_code == 200 and r.json()["started"] is True and seen == [["forex"]]
    seen.clear()
    client.post("/api/scanner/run")  # sem corpo: todos os mercados
    assert seen == [["acoes", "cripto", "forex"]]
    assert client.get("/api/scanner/status").json()["state"] in {"idle", "running", "done", "error"}


def test_latest_run_empty_then_with_hits_and_names(client):
    assert client.get("/api/scanner/runs/latest").json() == {"run": None, "hits": []}
    run_id = store.create_run(["acoes", "cripto"], [])
    base = {"setup_id": 1, "setup_name": "A", "direction": "alta", "price": 1.0, "details": {"rsi14": 50.0}}
    store.save_hits(
        run_id, [{**base, "market": "acoes", "symbol": "AAPL"}, {**base, "market": "cripto", "symbol": "BTCUSDT"}]
    )
    store.finish_run(run_id, "done", 2, 2, {}, {})

    body = client.get("/api/scanner/runs/latest").json()
    by_symbol = {h["symbol"]: h for h in body["hits"]}
    assert body["run"]["id"] == run_id
    assert by_symbol["AAPL"]["name"].startswith("Apple") and by_symbol["BTCUSDT"]["name"] is None
    assert client.get(f"/api/scanner/runs/{run_id}").status_code == 200
    assert client.get("/api/scanner/runs/999").status_code == 404
    assert client.get("/api/scanner/runs").json()[0]["id"] == run_id

    hit_id = by_symbol["AAPL"]["id"]
    assert client.post(f"/api/scanner/hits/{hit_id}/opened").status_code == 204
    assert client.post("/api/scanner/hits/9999/opened").status_code == 404
