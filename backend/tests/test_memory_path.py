from datetime import datetime, timezone

import pandas as pd
import pytest

from app.memory import path

CREATED = "2026-10-01T12:00:00+00:00"
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def bars(rows, start="2026-10-01 12:00"):
    """rows = [(open, high, low, close)] a cada hora, começando em `start` (UTC)."""
    idx = pd.date_range(start, periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx).assign(Volume=1.0)


def entry(**kw):
    base = dict(
        created_at=CREATED, horizon_days=10, direction="alta", entry_price=100.0, invalidation=95.0, target=110.0,
        status="invalidada", closed_at="2026-10-01T15:00:00+00:00", early_exit_at=None, early_exit_price=None,
        early_exit_r=None,
    )
    return {**base, **kw}


# 12h, 13h, 14h, 15h (a barra das 15h toca a invalidação), 16h (depois: o alvo)
LONG = [(100, 101, 99.5, 100.5), (100.5, 103, 100, 102), (102, 104, 98, 99), (99, 99.5, 94.5, 95), (95, 112, 95, 111)]


def test_case_window_uses_the_close_or_now_capped_by_the_horizon():
    closed = entry()
    start, end = path.case_window(closed, NOW)
    assert (start.isoformat(), end.isoformat()) == (CREATED, "2026-10-01T15:00:00+00:00")
    still_open = entry(status="aberta", closed_at=None)
    assert path.case_window(still_open, datetime(2026, 10, 4, tzinfo=timezone.utc))[1] == datetime(2026, 10, 4, tzinfo=timezone.utc)
    assert path.case_window(still_open, NOW)[1] == NOW  # 10/10 ainda está antes do fim do horizonte (11/10)
    late = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert path.case_window(still_open, late)[1] == datetime(2026, 10, 11, 12, tzinfo=timezone.utc)  # limitado ao fim do horizonte


def test_long_case_excursions_touches_and_trajectory_in_R():
    out = path.path_summary(entry(), bars(LONG), NOW)
    assert out["disponivel"] and out["granularidade"] == "1h" and out["barras"] == 4  # a barra das 16h é depois do fechamento
    assert out["excursao_a_favor_max_R"] == pytest.approx(0.8)  # (104 - 100) / 5
    assert out["excursao_contra_max_R"] == pytest.approx(-1.1)  # (94.5 - 100) / 5
    assert out["invalidacao_tocada_em"] == "2026-10-01T15:00:00+00:00"
    assert out["alvo_tocado_em"] is None  # o alvo só foi tocado depois do desfecho
    assert out["dias_ate_o_desfecho"] == 0.1
    assert out["trajetoria_diaria_R"] == [{"d": "2026-10-01", "r": -1.0}]
    assert out["saida_antecipada"] is None


def test_short_case_is_symmetric():
    rows = [(100, 100.5, 98, 99), (99, 101, 96, 97), (97, 105.5, 96.5, 105)]
    e = entry(direction="baixa", entry_price=100.0, invalidation=105.0, target=90.0, closed_at="2026-10-01T14:00:00+00:00")
    out = path.path_summary(e, bars(rows), NOW)
    assert out["excursao_a_favor_max_R"] == pytest.approx(0.8)  # (100 - 96) / 5
    assert out["excursao_contra_max_R"] == pytest.approx(-1.1)  # (100 - 105.5) / 5
    assert out["invalidacao_tocada_em"] == "2026-10-01T14:00:00+00:00"
    assert out["alvo_tocado_em"] is None


def test_early_exit_before_the_invalidation_and_what_happened_after():
    e = entry(early_exit_at="2026-10-01T14:00:00+00:00", early_exit_price=99.0, early_exit_r=-0.2)
    out = path.path_summary(e, bars(LONG), NOW)
    early = out["saida_antecipada"]
    assert early["invalidacao_tocada_antes"] is False  # até as 14h nenhuma barra tocou os 95
    assert early["depois_do_fechamento_da_tese"] is False
    assert early["r"] == -0.2 and early["preco"] == 99.0
    after = early["depois"]
    assert after["barras"] == 3  # 14h, 15h e 16h
    assert after["alvo_tocado_em"] == "2026-10-01T16:00:00+00:00"
    assert after["invalidacao_tocada_em"] == "2026-10-01T15:00:00+00:00"
    assert after["excursao_a_favor_max_R"] == pytest.approx(2.4)  # (112 - 100) / 5
    assert after["ultimo_fechamento_R"] == pytest.approx(2.2)  # (111 - 100) / 5


def test_early_exit_after_the_invalidation_was_touched_is_flagged():
    e = entry(early_exit_at="2026-10-01T16:00:00+00:00", early_exit_price=95.0, early_exit_r=-1.0)
    early = path.path_summary(e, bars(LONG), NOW)["saida_antecipada"]
    assert early["invalidacao_tocada_antes"] is True  # a barra das 15h já tinha tocado os 95
    assert early["depois_do_fechamento_da_tese"] is True  # a tese fechou às 15h e a saída foi registrada às 16h


def test_no_bars_in_the_window_is_reported_not_invented():
    far = bars(LONG, start="2026-11-01 12:00")
    out = path.path_summary(entry(), far, NOW)
    assert out["disponivel"] is False and "barras" in out["motivo"]
    assert path.path_summary(entry(), far.iloc[0:0], NOW)["disponivel"] is False


def test_long_trajectories_are_sampled_keeping_first_and_last_day():
    rows = [(100, 101, 99, 100 + i * 0.01) for i in range(24 * 40)]  # 40 dias
    e = entry(status="expirada", closed_at="2026-11-10T12:00:00+00:00", horizon_days=45)
    out = path.path_summary(e, bars(rows), datetime(2026, 12, 1, tzinfo=timezone.utc))
    traj = out["trajetoria_diaria_R"]
    assert len(traj) == path.MAX_DAILY_POINTS
    assert traj[0]["d"] == "2026-10-01" and traj[-1]["d"] == "2026-11-10"


# ---------- referências ----------


def closes():
    idx = pd.date_range("2026-09-25", "2026-10-10", freq="D")
    n = len(idx)
    frame = pd.DataFrame(
        {
            "^GSPC": 5000.0, "DX-Y.NYB": 100.0, "^VIX": 15.0, "^TNX": 4.0, "GC=F": 2000.0, "BTC-USD": 60000.0,
        },
        index=idx,
    )
    after = frame.index > pd.Timestamp("2026-10-01")
    frame.loc[after, "^GSPC"] = 5200.0  # +4,0%: notável
    frame.loc[after, "DX-Y.NYB"] = 100.5  # +0,5%
    frame.loc[after, "^VIX"] = 16.0  # +6,7%: abaixo do limite do VIX
    frame.loc[after, "^TNX"] = 4.2  # +0,2 ponto: notável
    frame.loc[after, "GC=F"] = 2100.0
    assert n == 16
    return frame


START, END = datetime(2026, 10, 2, 12, tzinfo=timezone.utc), datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def test_reference_moves_measure_from_the_close_before_the_registration():
    out = path.reference_moves(closes(), START, END, "forex")
    assert out["disponivel"] and out["de"] == "2026-10-01" and out["ate"] == "2026-10-07"  # só fechamentos já concluídos
    ins = out["instrumentos"]
    assert ins["sp500"]["variacao"] == 4.0 and ins["sp500"]["unidade"] == "%"
    assert (ins["sp500"]["de"], ins["sp500"]["ate"]) == ("2026-10-01", "2026-10-07")
    assert ins["juro10a"]["variacao"] == 0.2 and ins["juro10a"]["unidade"] == "pts"
    assert ins["vix"]["variacao"] == 6.67 and ins["dxy"]["variacao"] == 0.5
    assert sorted(out["notaveis"]) == ["juro10a", "ouro", "sp500"]  # ouro +5%; VIX e DXY ficam abaixo dos limites


def test_crypto_only_gets_the_crypto_references():
    ins = path.reference_moves(closes(), START, END, "cripto")["instrumentos"]
    assert "ouro" not in ins and "bitcoin" in ins and "sp500" in ins


def test_reference_moves_without_data_or_without_coverage():
    assert path.reference_moves(pd.DataFrame(), START, END, "acoes")["disponivel"] is False
    early_case = path.reference_moves(closes(), datetime(2026, 1, 5, tzinfo=timezone.utc), datetime(2026, 1, 9, tzinfo=timezone.utc), "acoes")
    assert early_case["disponivel"] is False and "cobert" in early_case["motivo"]


def test_reference_moves_never_use_a_close_that_had_not_happened_yet():
    frame = closes()
    # caso de 3 horas na manhã de 02/10 (08h-11h NY): o fechamento das 16h de 02/10 ainda não existia
    morning = path.reference_moves(frame, datetime(2026, 10, 2, 12, tzinfo=timezone.utc), datetime(2026, 10, 2, 15, tzinfo=timezone.utc), "acoes")
    assert morning["disponivel"] is False
    # começando às 21h UTC (17h NY, depois do fechamento) a base já é o próprio 02/10; termina em 05/10 de manhã: último fechamento = 04/10
    evening = path.reference_moves(frame, datetime(2026, 10, 2, 21, tzinfo=timezone.utc), datetime(2026, 10, 5, 12, tzinfo=timezone.utc), "acoes")
    assert evening["de"] == "2026-10-02" and evening["ate"] == "2026-10-04"
    assert evening["instrumentos"]["sp500"]["variacao"] == 0.0  # 5200 em ambos: o salto foi na véspera da base


def test_each_reference_reports_its_own_days_because_trading_calendars_differ():
    frame = closes()
    weekend = [pd.Timestamp("2026-10-03"), pd.Timestamp("2026-10-04")]  # sábado e domingo: o bitcoin negocia, o VIX não
    frame.loc[weekend, "^VIX"] = float("nan")
    out = path.reference_moves(frame, datetime(2026, 10, 2, 12, tzinfo=timezone.utc), datetime(2026, 10, 5, 12, tzinfo=timezone.utc), "acoes")
    assert out["instrumentos"]["vix"]["ate"] == "2026-10-02" and out["instrumentos"]["bitcoin"]["ate"] == "2026-10-04"
    assert out["de"] == "2026-10-01" and out["ate"] == "2026-10-04"  # o intervalo geral cobre todas
