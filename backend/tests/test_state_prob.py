import numpy as np
import pandas as pd
import pytest

from app.analysis.state_prob import MIN_N, conditional_probability, sample_non_overlapping, wilson


def synthetic(n=1500, seed=7, drift=0.0004):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    idx = pd.date_range("2018-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": 1e6}, index=idx
    )


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=0.001)
    assert hi == pytest.approx(0.5962, abs=0.001)
    assert all(np.isnan(x) for x in wilson(0, 0))


def test_sample_non_overlapping_keeps_min_distance():
    picked = sample_non_overlapping(np.array([0, 1, 2, 10, 11, 25]), 10)
    assert picked == [0, 10, 25]


def test_conditional_probability_structure_and_consistency():
    out = conditional_probability(synthetic(), horizon=10)
    assert 0 < out["base"] < 1
    assert out["label"] in {"alta", "baixa", "indistinta", "sem dados"}
    assert out["state_label"] and out["reason"]
    assert sum(1 for r in out["all_states"] if r["is_current"]) <= 1
    for r in out["all_states"]:
        if r["label"] == "sem dados":
            assert r["n"] < MIN_N and r["ci"] is None
        else:
            assert r["n"] >= MIN_N
            lo, hi = r["ci"]
            assert lo <= r["p_up"] <= hi


def test_labels_follow_confidence_interval_against_base():
    out = conditional_probability(synthetic(n=3000), horizon=5)
    for r in out["all_states"]:
        if r["label"] == "sem dados":
            continue
        lo, hi = r["ci"]
        if r["label"] == "alta":
            assert lo > out["base"]
        elif r["label"] == "baixa":
            assert hi < out["base"]
        else:
            assert lo <= out["base"] <= hi


def test_short_history_returns_no_data():
    out = conditional_probability(synthetic(n=60), horizon=10)
    assert out["label"] == "sem dados"
    assert out["reason"]
