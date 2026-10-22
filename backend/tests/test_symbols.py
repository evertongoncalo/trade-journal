import pytest

from app.providers.symbols import SymbolError, normalize, tradingview_symbol, yahoo_symbol


def test_normalize():
    assert normalize("cripto", "btc") == "BTCUSDT"
    assert normalize("cripto", "ETHBTC") == "ETHBTC"
    assert normalize("cripto", "SOLUSDT") == "SOLUSDT"
    assert normalize("forex", "eur/usd") == "EURUSD"
    assert normalize("acoes", " nvda ") == "NVDA"


@pytest.mark.parametrize(
    "market,symbol",
    [("forex", "EUR"), ("acoes", ""), ("acoes", "NV DA$"), ("bolsa", "NVDA")],
)
def test_normalize_rejects(market, symbol):
    with pytest.raises(SymbolError):
        normalize(market, symbol)


def test_yahoo_symbol():
    assert yahoo_symbol("forex", "EURUSD") == ("EURUSD=X", "")
    sym, note = yahoo_symbol("forex", "XAUUSD")
    assert sym == "GC=F" and "futuro" in note
    assert yahoo_symbol("cripto", "BTCUSDT")[0] == "BTC-USD"
    assert yahoo_symbol("cripto", "ETHBTC")[0] == "ETH-BTC"
    assert yahoo_symbol("acoes", "BRK.B")[0] == "BRK-B"


def test_tradingview_symbol():
    assert tradingview_symbol("cripto", "BTCUSDT") == "BINANCE:BTCUSDT"
    assert tradingview_symbol("forex", "XAUUSD") == "OANDA:XAUUSD"
    assert tradingview_symbol("acoes", "NVDA", "NMS") == "NASDAQ:NVDA"
    assert tradingview_symbol("acoes", "JPM", "NYQ") == "NYSE:JPM"
    assert tradingview_symbol("acoes", "BRK-B", "NYQ") == "NYSE:BRK.B"
    assert tradingview_symbol("acoes", "XYZ", None) == "XYZ"
