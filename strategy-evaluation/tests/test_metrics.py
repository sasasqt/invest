import math

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.metrics import (
    benchmark_metrics,
    drawdown_metrics,
    episode_metrics,
    instrument_returns,
    period_rate,
    return_metrics,
    tail_metrics,
)


def test_benchmark_gap_does_not_create_a_multi_session_daily_return():
    sessions = pd.bdate_range("2024-01-01", periods=30)
    bars = pd.DataFrame(
        {"date": sessions, "instrument": "SPY", "close": 100 * 1.01 ** np.arange(30)}
    )
    bars = bars.drop(index=10)
    benchmark = instrument_returns(bars, sessions=sessions)
    assert benchmark.loc[sessions[[0, 10, 11]]].isna().all()
    assert benchmark.loc[sessions[12]] == pytest.approx(0.01)
    # Constant 1% daily strategy and benchmark must have zero tracking error.
    metrics = benchmark_metrics(pd.Series(0.01, index=sessions), benchmark, 252)
    assert metrics["tracking_error"].value == pytest.approx(0, abs=1e-12)
    assert metrics["benchmark_total_return"].extra["aligned_sessions"] == 27


def series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def val(m, key):
    return m[key].value


def test_core_return_metrics_against_hand_calculation():
    r = np.array([0.01, -0.02, 0.015, 0.005, -0.01, 0.02, 0.0, -0.005])
    m = return_metrics(series(r), v0=100.0, annualization=252, risk_free_annual=0.0)
    assert val(m, "mean_return") == pytest.approx(r.mean())
    assert val(m, "variance_return") == pytest.approx(r.var(ddof=1))
    assert val(m, "annual_volatility") == pytest.approx(r.std(ddof=1) * math.sqrt(252))
    assert val(m, "sharpe") == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))
    dd = math.sqrt(np.mean(np.minimum(r, 0) ** 2))  # all-period denominator
    assert val(m, "downside_deviation") == pytest.approx(dd)
    assert val(m, "sortino") == pytest.approx(r.mean() * 252 / (dd * math.sqrt(252)))
    total = np.prod(1 + r) - 1
    assert val(m, "total_return") == pytest.approx(total)
    assert val(m, "cagr") == pytest.approx((1 + total) ** (252 / len(r)) - 1)
    gains, losses = np.maximum(r, 0).sum(), np.maximum(-r, 0).sum()
    assert val(m, "omega") == pytest.approx(gains / losses)
    assert val(m, "gain_to_pain") == pytest.approx(r.sum() / losses)
    assert val(m, "hit_rate") == pytest.approx(4 / 8)


def test_risk_free_and_mar_are_converted_to_period_rates():
    r = series([0.001, 0.002, -0.001, 0.0005] * 10)
    rf = period_rate(0.05, 252)
    assert rf == pytest.approx(1.05 ** (1 / 252) - 1)
    m = return_metrics(r, v0=1.0, annualization=252, risk_free_annual=0.05, mar_annual=0.05)
    ex = r - rf
    assert val(m, "sharpe") == pytest.approx(ex.mean() / ex.std(ddof=1) * math.sqrt(252))
    assert m["downside_deviation"].extra["mar_period"] == pytest.approx(rf)


def test_drawdown_includes_initial_value_and_records_dates():
    # Wealth path from V0=100: 90 (dd 10%), 95, 80 (dd 20%), 100 (recover), 110.
    w = series([90, 95, 80, 100, 110])
    m = drawdown_metrics(w, 100.0)
    assert m["max_drawdown"].value == pytest.approx(0.2)
    assert m["max_drawdown"].extra["peak_date"] == "start"
    assert m["max_drawdown"].extra["trough_date"] == "2024-01-03"
    assert m["max_drawdown"].extra["recovery_date"] == "2024-01-04"
    assert m["max_drawdown_duration"].value == 4
    assert m["max_recovery_duration"].value == 1
    dd = np.array([-0.1, -0.05, -0.2, 0.0, 0.0])
    assert m["ulcer_index"].value == pytest.approx(math.sqrt(np.mean(dd**2)))
    assert m["time_under_water"].value == pytest.approx(0.6)


def test_unrecovered_drawdown_is_censored():
    m = drawdown_metrics(series([100, 120, 90, 100]), 100.0)
    assert m["max_drawdown"].value == pytest.approx(0.25)
    assert m["max_drawdown"].extra["recovery_date"] is None
    assert m["max_drawdown_duration"].extra["censored"] is True
    assert m["current_drawdown"].value == pytest.approx(1 - 100 / 120)


def test_calmar_uses_cagr_over_max_drawdown():
    r = series([0.01, -0.03, 0.02, 0.01, 0.005] * 6)
    m = return_metrics(r, v0=1.0, annualization=252)
    assert val(m, "calmar") == pytest.approx(val(m, "cagr") / val(m, "max_drawdown"))


def test_undefined_results_are_explicit():
    flat = return_metrics(series([0.0] * 30), v0=1.0, annualization=252)
    assert flat["sharpe"].status == "undefined" and flat["sharpe"].value is None
    assert flat["sortino"].status == "undefined"
    assert flat["calmar"].reason == "zero_max_drawdown"
    up = return_metrics(series([0.01, 0.02] * 15), v0=1.0, annualization=252)
    assert up["omega"].reason == "no_returns_below_mar"
    one = return_metrics(series([0.01]), v0=1.0, annualization=252)
    assert one["status"].status == "insufficient_data"


def test_insolvency_invalidates_growth_ratios():
    m = return_metrics(series([0.1, -1.0, 0.0]), v0=1.0, annualization=252)
    assert m["insolvency"].value == "2024-01-02"
    assert m["cagr"].status == "invalid_input" and m["sharpe"].value is None
    assert m["cagr"].unit == "fraction/year"
    assert m["total_return"].value == -1.0
    assert m["max_drawdown"].value == 1.0


def test_var_and_expected_shortfall():
    r = np.linspace(-0.05, 0.05, 101)  # losses 0.05 .. -0.05
    t = tail_metrics(r)
    assert t["var_loss_95"].value == pytest.approx(np.quantile(-r, 0.95))
    assert t["expected_shortfall_95"].value == pytest.approx(
        np.mean([0.05, 0.049, 0.048, 0.047, 0.046, 0.045])
    )
    assert t["skewness"].value == pytest.approx(0.0, abs=1e-12)
    assert tail_metrics(r[:10])["var_loss_95"].status == "insufficient_data"


def test_trade_episode_metrics():
    ep = pd.DataFrame(
        {
            "side": ["long", "long", "short", "short", "long"],
            "pnl": [100.0, -50.0, 0.0, 30.0, 999.0],
            "holding_sessions": [5, 3, 2, 4, 1],
            "status": ["closed", "closed", "closed", "closed", "open"],
        }
    )
    m = episode_metrics(ep, flat_tolerance=1e-6)
    assert (m["closed_trades"].value, m["open_trades"].value) == (4, 1)
    assert (m["wins"].value, m["losses"].value, m["flats"].value) == (2, 1, 1)
    assert m["win_rate"].value == pytest.approx(0.5)
    assert m["non_flat_win_rate"].value == pytest.approx(2 / 3)
    assert m["profit_factor"].value == pytest.approx(130 / 50)
    assert m["payoff_ratio"].value == pytest.approx(65 / 50)
    assert m["average_trade_pnl"].value == pytest.approx(80 / 4)
    no_loss = episode_metrics(ep.iloc[[0, 3]], 1e-6)
    assert no_loss["profit_factor"].status == "undefined"
    assert episode_metrics(ep.iloc[[4]], 1e-6)["win_rate"].reason == "no_closed_trades"
