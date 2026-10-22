from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.journal.evaluate import Plan, evaluate_plan, r_multiple, validate_plan

START = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)


def bars(rows, first=START + timedelta(hours=1)):
    idx = pd.date_range(first, periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx).assign(Volume=0.0)


def long_plan(horizon=10):
    return Plan("alta", 100.0, 95.0, 110.0, START, horizon)


def short_plan(horizon=10):
    return Plan("baixa", 100.0, 105.0, 90.0, START, horizon)


def test_long_hits_target():
    b = bars([(100, 102, 99, 101), (101, 111, 100, 110)])
    out = evaluate_plan(long_plan(), b, now=START + timedelta(hours=5))
    assert (out.status, out.exit_price, out.r) == ("alvo", 110.0, 2.0)
    assert out.closed_at == b.index[1].to_pydatetime()


def test_long_hits_invalidation():
    out = evaluate_plan(long_plan(), bars([(100, 101, 94, 95)]), now=START + timedelta(hours=5))
    assert (out.status, out.exit_price, out.r) == ("invalidada", 95.0, -1.0)


def test_same_bar_counts_invalidation_first():
    out = evaluate_plan(long_plan(), bars([(100, 112, 94, 100)]), now=START + timedelta(hours=5))
    assert out.status == "invalidada"


def test_gap_below_invalidation_executes_at_open():
    out = evaluate_plan(long_plan(), bars([(93, 94, 92, 93)]), now=START + timedelta(hours=5))
    assert out.status == "invalidada"
    assert out.exit_price == 93.0
    assert out.r == pytest.approx(-1.4)


def test_gap_above_target_executes_at_open():
    out = evaluate_plan(long_plan(), bars([(112, 113, 111, 112)]), now=START + timedelta(hours=5))
    assert (out.status, out.exit_price) == ("alvo", 112.0)
    assert out.r == pytest.approx(2.4)


def test_expires_at_last_close_when_horizon_passes():
    b = bars([(100, 102, 99, 101), (101, 103, 100, 102), (102, 104, 101, 103)])
    out = evaluate_plan(long_plan(horizon=1), b, now=START + timedelta(days=2))
    assert out.status == "expirada"
    assert out.exit_price == 103.0
    assert out.r == pytest.approx(0.6)


def test_stays_open_before_horizon_without_hits():
    out = evaluate_plan(long_plan(), bars([(100, 102, 99, 101)]), now=START + timedelta(hours=3))
    assert out.status == "aberta"


def test_open_when_no_bars_even_after_horizon():
    empty = bars([(100, 102, 99, 101)]).iloc[0:0]
    assert evaluate_plan(long_plan(horizon=1), empty, now=START + timedelta(days=5)).status == "aberta"


def test_short_target_and_invalidation():
    hit = evaluate_plan(short_plan(), bars([(100, 101, 89, 90)]), now=START + timedelta(hours=5))
    assert (hit.status, hit.exit_price, hit.r) == ("alvo", 90.0, 2.0)
    stop = evaluate_plan(short_plan(), bars([(100, 106, 99, 105)]), now=START + timedelta(hours=5))
    assert (stop.status, stop.exit_price, stop.r) == ("invalidada", 105.0, -1.0)


def test_bars_before_registration_are_ignored():
    early = bars([(100, 120, 80, 100)], first=START - timedelta(hours=3))  # tocaria alvo e invalidação
    later = bars([(100, 101, 99, 100)])
    out = evaluate_plan(long_plan(), pd.concat([early, later]), now=START + timedelta(hours=3))
    assert out.status == "aberta"


@pytest.mark.parametrize(
    "plan",
    [
        Plan("alta", 100, 105, 110, START, 5),  # invalidação acima da entrada
        Plan("alta", 100, 95, 98, START, 5),  # alvo abaixo da entrada
        Plan("baixa", 100, 95, 90, START, 5),  # invalidação abaixo da entrada
        Plan("alta", 100, 95, 110, START, 0),  # horizonte inválido
        Plan("lado", 100, 95, 110, START, 5),  # direção inválida
    ],
)
def test_validate_plan_rejects_inconsistent_plans(plan):
    with pytest.raises(ValueError):
        validate_plan(plan)


def test_r_multiple_short_is_mirrored():
    assert r_multiple(short_plan(), 95.0) == pytest.approx(1.0)
    assert r_multiple(short_plan(), 110.0) == pytest.approx(-2.0)
