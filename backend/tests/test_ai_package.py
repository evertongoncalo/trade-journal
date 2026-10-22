from datetime import date

import numpy as np
import pandas as pd
import pytest

from app import db
from app.ai import fundamentals, macro, package
from app.analysis import price_action
from app.correlation import store as corr_store
from app.providers import registry
from app.providers.base import PriceHistory


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def ohlcv(n=400, seed=2, drift=0.002, start="2025-01-01"):
    rng = np.random.default_rng(seed)
    close = 50 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": close * 0.999, "High": close * 1.006, "Low": close * 0.994, "Close": close, "Volume": 1e6}, index=idx
    )


# ---------- price action ----------


def zigzag(up=True):
    """Onda com amplitude fixa sobre uma tendência: topos e fundos claramente ascendentes (ou descendentes)."""
    x = np.arange(240)
    price = 100 + (0.15 if up else -0.15) * x + 6 * np.sin(x / 4)
    idx = pd.date_range("2025-01-01", periods=len(x), freq="D", tz="UTC")
    return pd.DataFrame({"Open": price, "High": price + 0.5, "Low": price - 0.5, "Close": price, "Volume": 1.0}, index=idx)


def test_pivots_alternate_and_structure_follows_the_trend():
    pts = price_action.pivots(zigzag(up=True))
    assert {p["tipo"] for p in pts} == {"topo", "fundo"} and all(a["i"] < b["i"] for a, b in zip(pts, pts[1:]))
    assert price_action.structure(pts) == "topos e fundos ascendentes"
    assert price_action.structure(price_action.pivots(zigzag(up=False))) == "topos e fundos descendentes"
    assert price_action.structure([]) == "indefinida"
    mixed = [{"tipo": "topo", "preco": 10}, {"tipo": "topo", "preco": 12}, {"tipo": "fundo", "preco": 5}, {"tipo": "fundo", "preco": 4}]
    assert price_action.structure(mixed).startswith("misto")


def test_price_action_summary_levels_and_bars():
    df = zigzag(up=True)
    s = price_action.summarize(df)
    close = float(df["Close"].iloc[-1])
    assert s["ultimo_fechamento"] == pytest.approx(close, rel=1e-4)
    assert s["estrutura"] == "topos e fundos ascendentes"
    assert s["resistencia_proxima"]["preco"] > close and s["suporte_proximo"]["preco"] < close
    assert s["resistencia_proxima"]["dist_atr"] > 0
    assert 0 <= s["posicao_no_range_52s"] <= 1
    assert s["minima_52s"] <= close <= s["maxima_52s"]
    rows = s["ultimas_barras"]["linhas"]
    assert len(rows) == price_action.RECENT_BARS and s["ultimas_barras"]["colunas"][-1] == "fechamento"
    assert rows[-1][0] == df.index[-1].date().isoformat() and len(s["pivos_recentes"]) <= 6


def test_price_action_with_short_history_does_not_crash():
    s = price_action.summarize(ohlcv(n=30))
    assert s["variacao_pct"]["60d"] is None and s["variacao_pct"]["20d"] is not None
    assert isinstance(s["estrutura"], str) and len(s["ultimas_barras"]["linhas"]) == 30
    assert s["resistencia_proxima"] is None or s["resistencia_proxima"]["preco"] > s["ultimo_fechamento"]


# ---------- macro ----------


def test_macro_unavailable_until_the_universe_is_downloaded():
    out = macro.snapshot()
    assert out["disponivel"] is False and "Atualizar universo" in out["motivo"]


def test_macro_snapshot_changes_and_crypto_subset():
    idx = pd.bdate_range("2026-01-01", periods=80)
    corr_store.save_closes("DX-Y.NYB", pd.Series(np.linspace(100, 104, 80), index=idx))
    corr_store.save_closes("^TNX", pd.Series(np.linspace(4.0, 4.8, 80), index=idx))
    corr_store.save_closes("GC=F", pd.Series(np.linspace(2000, 2100, 80), index=idx))
    out = macro.snapshot()
    assert out["disponivel"] and out["ate"] == idx[-1].date().isoformat()
    dxy, juro = out["instrumentos"]["dxy"], out["instrumentos"]["juro10a"]
    assert dxy["unidade_da_variacao"] == "%" and dxy["var_20d"] == pytest.approx((104 / np.linspace(100, 104, 80)[-21] - 1) * 100, abs=0.01)
    assert juro["unidade_da_variacao"] == "pts" and juro["var_20d"] == pytest.approx(4.8 - np.linspace(4.0, 4.8, 80)[-21], abs=0.001)
    assert "vix" not in out["instrumentos"]  # o que não está no universo simplesmente não entra
    crypto = macro.snapshot(macro.CRYPTO_KEYS)
    assert set(crypto["instrumentos"]) == {"dxy", "juro10a"}  # ouro fica de fora do recorte de cripto


# ---------- fundamentos ----------


class FakeTicker:
    info: dict = {}
    calendar: dict | None = {}

    def __init__(self, sym):
        self.sym = sym


@pytest.fixture(autouse=True)
def clear_fundamentals_cache():
    fundamentals._fetch_cached.cache_clear()


def test_fundamentals_for_a_stock_with_next_earnings(monkeypatch):
    class T(FakeTicker):
        info = {"quoteType": "EQUITY", "shortName": "Acme", "trailingPE": 25.123456, "debtToEquity": 16.97, "targetMeanPrice": 300, "recommendationKey": "buy", "numberOfAnalystOpinions": 40}
        calendar = {"Earnings Date": [date(2026, 11, 17), date(2026, 8, 1)]}

    monkeypatch.setattr(fundamentals.yf, "Ticker", T)
    out = fundamentals.fetch("ACME", today=date(2026, 10, 22))
    assert out["disponivel"] and out["nome"] == "Acme" and out["pl_12m"] == 25.1235
    assert out["proximo_resultado"] == "2026-11-17" and out["dias_ate_o_resultado"] == 26  # ignora datas passadas
    assert out["analistas_opiniao_de_terceiros"]["recomendacao"] == "buy"
    assert "percentual" in out["unidades"] and "dividend_yield" not in out


def test_fundamentals_unavailable_for_etfs_failures_and_missing_calendar(monkeypatch):
    class Etf(FakeTicker):
        info = {"quoteType": "ETF"}

    monkeypatch.setattr(fundamentals.yf, "Ticker", Etf)
    out = fundamentals.fetch("SPY", today=date(2026, 10, 22))
    assert out["disponivel"] is False and "ETF" in out["motivo"]

    class Boom(FakeTicker):
        @property
        def info(self):
            raise RuntimeError("Yahoo fora do ar")

    fundamentals._fetch_cached.cache_clear()
    monkeypatch.setattr(fundamentals.yf, "Ticker", Boom)
    out = fundamentals.fetch("XYZ", today=date(2026, 10, 22))
    assert out["disponivel"] is False and "Yahoo fora do ar" in out["motivo"]

    class NoCal(FakeTicker):
        info = {"quoteType": "EQUITY", "shortName": "Sem data"}
        calendar = None

    fundamentals._fetch_cached.cache_clear()
    monkeypatch.setattr(fundamentals.yf, "Ticker", NoCal)
    out = fundamentals.fetch("NOCAL", today=date(2026, 10, 22))
    assert out["disponivel"] and out["proximo_resultado"] is None and out["dias_ate_o_resultado"] is None


# ---------- montagem do pacote ----------


def patch_sources(monkeypatch, age_minutes=5):
    daily = ohlcv()
    now = pd.Timestamp.now(tz="UTC").floor("h")
    hourly = ohlcv(n=5).set_index(pd.date_range(end=now - pd.Timedelta(minutes=age_minutes), periods=5, freq="h"))

    def fake_fetch(market, symbol, interval, days):
        return PriceHistory(daily if interval == "1d" else hourly, "fake", symbol, interval, note="nota da fonte")

    monkeypatch.setattr(registry, "fetch", fake_fetch)
    monkeypatch.setattr(package.correlation_service, "panel_payload", lambda m, s: {
        "universe": {"state": "ok", "updated_at": "2026-10-22T10:00:00+00:00"},
        "fixed": [
            {"symbol": "^GSPC", "label": "S&P 500", "status": "estável", "mechanical": False, "corr_full": 0.7, "stability": 1.0, "beta": 1.9, "z20": -0.4},
            {"symbol": "DX-Y.NYB", "label": "DXY", "status": "mecânica", "mechanical": True, "corr_full": -0.98},
        ],
        "discovered": [
            {"name": "Risco e índices", "items": [
                {"label": "VIX", "status": "estável", "mechanical": False, "corr_full": -0.59, "corr_250": -0.54, "stability": 1.0, "beta": -2.0, "z20": 0.1},
                {"label": "Ruído", "status": "sem relação estável", "mechanical": False, "corr_full": 0.2},
            ]},
            {"name": "Setores (EUA)", "items": [{"label": "XLK", "status": "mecânica", "mechanical": True, "corr_full": 0.79}]},
        ],
        "parecer": {"lines": ["S&P 500: correlação +0,70"]},
    })
    monkeypatch.setattr(fundamentals, "fetch", lambda sym: {"disponivel": True, "pl_12m": 20})


def test_build_returns_only_the_requested_slices_with_common_part(monkeypatch):
    patch_sources(monkeypatch)
    pkg = package.build("acoes", "nvda", 10, {"indicadores", "price_action", "correlacao", "fundamentos"})
    assert set(pkg["fatias"]) == {"indicadores", "price_action", "correlacao", "fundamentos"}
    assert pkg["ativo"]["simbolo"] == "NVDA" and pkg["ativo"]["horizonte_dias"] == 10
    assert pkg["saude_dados"]["diario"]["fonte"].startswith("fake:") and pkg["saude_dados"]["intradiario"]["idade_da_ultima_barra_min"] < 120
    assert pkg["avisos"] == ["nota da fonte"]  # a nota igual do diário e do intradiário aparece uma vez só
    assert pkg["fatias"]["fundamentos"] == {"disponivel": True, "pl_12m": 20}


def test_indicators_slice_contains_values_series_and_labeled_probability(monkeypatch):
    patch_sources(monkeypatch)
    sl = package.build("acoes", "NVDA", 10, {"indicadores"})["fatias"]["indicadores"]
    assert 0 <= sl["valores"]["rsi14"] <= 100 and "bars" not in sl["valores"]
    assert len(sl["rsi14_ultimos_10"]) == 10 and len(sl["macd_hist_ultimos_10"]) == 10
    prob = sl["probabilidade"]
    assert prob["rotulo"] in {"alta", "baixa", "indistinta", "sem_dados"} and prob["base_do_ativo"] is not None
    assert "10 dias" in prob["descricao"]


def test_correlation_slice_keeps_stable_non_mechanical_relations_only(monkeypatch):
    patch_sources(monkeypatch)
    sl = package.build("acoes", "NVDA", 10, {"correlacao"})["fatias"]["correlacao"]
    assert sl["disponivel"] and set(sl["referencias_fixas"]) == {"sp500", "dxy"}
    assert sl["referencias_fixas"]["dxy"]["status"] == "mecânica"
    assert [d["label"] for d in sl["descobertas_estaveis"]] == ["VIX"]
    assert sl["parecer_do_codigo"] == ["S&P 500: correlação +0,70"]


def test_correlation_slice_reports_unavailable_universe_and_errors(monkeypatch):
    patch_sources(monkeypatch)
    monkeypatch.setattr(package.correlation_service, "panel_payload", lambda m, s: {"universe": {"state": "vazio"}})
    out = package.correlation_slice("acoes", "NVDA")
    assert out["disponivel"] is False and "Atualizar universo" in out["motivo"]

    def boom(m, s):
        raise RuntimeError("sem preço")

    monkeypatch.setattr(package.correlation_service, "panel_payload", boom)
    assert "sem preço" in package.correlation_slice("acoes", "NVDA")["motivo"]


def test_closed_market_adds_a_warning_and_fundamentals_only_exist_for_stocks(monkeypatch):
    patch_sources(monkeypatch, age_minutes=900)
    pkg = package.build("forex", "EURUSD", 10, {"fundamentos", "par"})
    assert any("mercado pode estar fechado" in a for a in pkg["avisos"])
    assert pkg["fatias"]["fundamentos"]["disponivel"] is False
    assert pkg["fatias"]["par"] == {"tipo": "par de moedas", "base": "EUR", "cotacao": "USD"}
    gold = package.pair_slice("forex", "XAUUSD")
    assert gold["tipo"].startswith("metal") and package.pair_slice("acoes", "NVDA")["disponivel"] is False


def test_package_is_json_safe(monkeypatch):
    import json

    patch_sources(monkeypatch)
    pkg = package.build("cripto", "BTC", 10, {"indicadores", "price_action", "macro"})
    json.dumps(pkg, allow_nan=False)  # sem NaN nem tipos numpy
    assert pkg["ativo"]["nome"] is None and pkg["fatias"]["macro"]["disponivel"] is False
