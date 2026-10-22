from datetime import datetime, timedelta, timezone

import pandas as pd

from app.alerts import evaluate as ev

T0 = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)


def minute_bars(rows, start=T0):
    """rows = [(high, low, close)] em barras de 1 minuto a partir de `start`."""
    idx = pd.date_range(start, periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame(
        [(c, h, lo, c, 0.0) for h, lo, c in rows], columns=["Open", "High", "Low", "Close", "Volume"], index=idx
    )


def alert(**kw):
    base = {
        "id": 1, "created_at": (T0 - timedelta(seconds=30)).isoformat(), "price": 100.0,
        "direction": "acima", "checked_until": None,
    }
    return {**base, **kw}


def test_wick_above_the_level_triggers_even_if_the_close_stays_below():
    bars = minute_bars([(99.0, 98.0, 98.5), (100.2, 98.5, 99.0), (99.5, 98.8, 99.2)])
    hit = ev.first_touch(alert(), bars, "1m")
    assert hit["bar"] == T0 + timedelta(minutes=1)
    assert hit["extreme"] == 100.2 and hit["close"] == 99.0


def test_wick_below_the_level_triggers_a_down_alert():
    bars = minute_bars([(101, 100.5, 100.8), (101, 99.7, 100.6)])
    hit = ev.first_touch(alert(direction="abaixo"), bars, "1m")
    assert hit["bar"] == T0 + timedelta(minutes=1) and hit["extreme"] == 99.7


def test_no_touch_returns_none():
    bars = minute_bars([(99.5, 98.0, 99.0), (99.9, 98.5, 99.5)])
    assert ev.first_touch(alert(), bars, "1m") is None
    assert ev.first_touch(alert(direction="abaixo", price=95), bars, "1m") is None


def test_touching_the_exact_level_counts():
    assert ev.first_touch(alert(), minute_bars([(100.0, 99.0, 99.5)]), "1m") is not None
    assert ev.first_touch(alert(direction="abaixo", price=99.0), minute_bars([(100.0, 99.0, 99.5)]), "1m") is not None


def test_first_bar_to_touch_wins():
    bars = minute_bars([(99, 98, 98.5), (101, 99, 100.5), (105, 100, 104)])
    assert ev.first_touch(alert(), bars, "1m")["bar"] == T0 + timedelta(minutes=1)


def test_bars_that_began_before_the_alert_was_created_are_ignored():
    created = (T0 + timedelta(seconds=30)).isoformat()  # criado no meio da barra das 15:00
    bars = minute_bars([(105.0, 98.0, 99.0), (99.5, 98.5, 99.0), (101.0, 99.0, 100.5)])
    hit = ev.first_touch(alert(created_at=created), bars, "1m")
    assert hit["bar"] == T0 + timedelta(minutes=2)  # a barra das 15:00 (com 105) não conta


def test_checked_until_skips_what_was_already_verified_but_rechecks_that_bar():
    bars = minute_bars([(101, 99, 100), (99, 98, 98.5), (99.5, 98, 99), (100.5, 99, 100.2)])
    checked = (T0 + timedelta(minutes=2)).isoformat()
    hit = ev.first_touch(alert(checked_until=checked), bars, "1m")
    assert hit["bar"] == T0 + timedelta(minutes=3)  # o toque das 15:00 já ficou para trás
    # a barra de checked_until (ainda em formação no ciclo anterior) é avaliada de novo
    bars2 = minute_bars([(101, 99, 100), (99, 98, 98.5), (100.1, 98, 99)])
    assert ev.first_touch(alert(checked_until=checked), bars2, "1m")["bar"] == T0 + timedelta(minutes=2)


def test_checked_until_after_returns_the_start_of_the_last_bar():
    bars = minute_bars([(99, 98, 98.5), (99, 98, 98.6), (99, 98, 98.7)])
    assert ev.checked_until_after(alert(), bars, "1m") == T0 + timedelta(minutes=2)
    old = bars.iloc[:0]
    assert ev.checked_until_after(alert(), old, "1m") is None
    only_past = minute_bars([(99, 98, 98.5)], start=T0 - timedelta(hours=1))
    assert ev.checked_until_after(alert(), only_past, "1m") is None  # nada depois da criação


def test_ceil_to_rounds_up_to_the_next_bar_boundary():
    t = datetime(2026, 1, 5, 15, 7, 20, tzinfo=timezone.utc)
    assert ev.ceil_to(t, "1m") == datetime(2026, 1, 5, 15, 8, tzinfo=timezone.utc)
    assert ev.ceil_to(t, "1h") == datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)
    assert ev.ceil_to(t, "1d") == datetime(2026, 1, 6, 0, 0, tzinfo=timezone.utc)
    exact = datetime(2026, 1, 5, 15, 8, tzinfo=timezone.utc)
    assert ev.ceil_to(exact, "1m") == exact


def test_parse_ts_assumes_utc_when_naive():
    assert ev.parse_ts("2026-01-05T15:00:00").tzinfo is not None
    assert ev.parse_ts("2026-01-05T15:00:00+01:00").utcoffset() == timedelta(hours=1)
