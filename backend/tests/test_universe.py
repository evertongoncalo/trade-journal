from app.correlation.universe import CANDIDATES, DXY, FIXED, fx_currencies, is_mechanical


def test_fx_currencies():
    assert fx_currencies("EURUSD=X") == {"EUR", "USD"}
    assert fx_currencies("GC=F") == set()
    assert fx_currencies("^GSPC") == set()


def test_mechanical_forex_pairs_with_shared_currency():
    assert is_mechanical("EURUSD=X", "GBPUSD=X")  # perna USD em comum
    assert is_mechanical("EURJPY=X", "EURGBP=X")  # perna EUR em comum
    assert not is_mechanical("EURUSD=X", "AUDNZD=X")


def test_mechanical_dxy_against_usd_pairs_only():
    assert is_mechanical("EURUSD=X", DXY)
    assert is_mechanical(DXY, "USDJPY=X")
    assert not is_mechanical("AUDNZD=X", DXY)
    assert not is_mechanical("GC=F", DXY)  # ouro x dólar é relação econômica, não mecânica


def test_mechanical_stock_against_its_own_sector_etf():
    assert is_mechanical("NVDA", "XLK", frozenset({"XLK", "SMH"}))
    assert not is_mechanical("NVDA", "XLF", frozenset({"XLK"}))
    assert not is_mechanical("NVDA", "^GSPC", frozenset({"XLK"}))


def test_universe_has_no_duplicates_and_contains_fixed_references():
    symbols = [i.symbol for i in CANDIDATES]
    assert len(symbols) == len(set(symbols)) >= 40
    assert all(s in symbols for s, _ in FIXED)
