import math
import warnings

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


@pytest.mark.parametrize("aligned", [0, 19, 20])
def test_benchmark_coverage_is_recorded_on_both_sides_of_minimum_sample(aligned):
    sessions = pd.bdate_range("2024-01-01", periods=30)
    strategy = pd.Series(0.001, index=sessions)
    benchmark = pd.Series(0.002, index=sessions[30 - aligned :])
    metrics = benchmark_metrics(strategy, benchmark, 252, label="SPY")
    metric = metrics["benchmark"] if aligned < 20 else metrics["benchmark_total_return"]
    assert metric.extra == {
        "benchmark": "SPY",
        "aligned_sessions": aligned,
        "evaluation_sessions": 30,
    }
    if aligned < 20:
        assert metric.status == "insufficient_data"
        assert metric.reason == "fewer_than_20_aligned_returns"
        assert metric.value is None
    else:
        assert metric.status == "ok"
        assert metric.value == pytest.approx(1.002**20 - 1)


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


@pytest.mark.parametrize(
    ("wealth", "longest", "censored"),
    [
        # From V0 = 100: the first episode runs from V0 to 101 (3 sessions, recovered); the
        # second starts at 101 and is 1 session old at the end. The maximum is exact.
        ([90, 95, 101, 100.5], 3, False),
        ([90, 95, 101, 100.5, 100.8], 3, False),  # open episode 2 sessions, still shorter
        ([90, 95, 101, 100.5, 100.8, 100.9], 3, True),  # tie: the open one can still grow
        ([90, 95, 101, 100.5, 100.8, 100.9, 100], 4, True),  # the open one is the longest
        ([90, 95, 101, 0], 3, False),  # insolvent at the end, open episode 1 session
        ([101, 0, 0, 0], 3, True),  # insolvent, the open episode (from 101) is the longest
        ([100, 101, 101, 105], 0, False),  # never under water
        ([99], 1, True),  # one session, under water
    ],
)
def test_censored_flag_describes_the_longest_drawdown(
    wealth: list[float], longest: int, censored: bool
) -> None:
    """BH-2026-10-14-8: `censored` qualifies the reported maximum, so it is set only when the
    longest episode is the one still open at the end (METRICS.md section 6), not whenever
    the last episode is open."""
    duration = drawdown_metrics(series(wealth), 100.0)["max_drawdown_duration"]
    assert duration.value == longest
    assert duration.extra is not None
    assert duration.extra["censored"] is censored


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


def test_var_and_expected_shortfall() -> None:
    r = np.linspace(-0.05, 0.05, 101)  # losses 0.05 .. -0.05
    t = tail_metrics(r)
    assert t["var_loss_95"].value == pytest.approx(np.quantile(-r, 0.95))
    # Tail mass 0.05 * 101 = 5.05 observations: the five largest losses whole, 5 % of the sixth.
    es = t["expected_shortfall_95"]
    assert es.value == pytest.approx((0.05 + 0.049 + 0.048 + 0.047 + 0.046 + 0.05 * 0.045) / 5.05)
    assert es.extra["estimator"] == "acerbi_tasche"
    assert es.extra["tail_probability"] == pytest.approx(0.05)
    assert es.extra["tail_mass"] == pytest.approx(5.05)
    assert es.extra["tail_observations"] == 6
    assert t["skewness"].value == pytest.approx(0.0, abs=1e-12)
    assert tail_metrics(r[:10])["var_loss_95"].status == "insufficient_data"


def test_expected_shortfall_ties_use_the_tail_mass_not_every_tied_loss() -> None:
    # BH-2026-11-03-1: 100 sessions, 3 losses of 1 %, 90 flat, 7 gains. VaR sits on the flat
    # value; the 5 % tail is five observations (the three losses and two flat sessions), so
    # ES = 0.03 / 5, not the mean of the 93 sessions at or above VaR.
    t = tail_metrics(np.array([-0.01] * 3 + [0.0] * 90 + [0.005] * 7))
    es = t["expected_shortfall_95"]
    assert t["var_loss_95"].value == pytest.approx(0.0)
    assert es.value == pytest.approx(0.006)
    assert es.extra["tail_observations"] == 5
    assert es.extra["tail_mass"] == pytest.approx(5.0)


def test_expected_shortfall_with_ties_at_var_and_with_a_negative_var() -> None:
    # Ties at VaR: losses 2 x 0.03, 8 x 0.01, 90 x 0 give VaR 0.01; the worst five by rank are
    # the two 0.03 losses and three of the 0.01 losses.
    t = tail_metrics(-np.array([0.03] * 2 + [0.01] * 8 + [0.0] * 90))
    assert t["var_loss_95"].value == pytest.approx(0.01)
    assert t["expected_shortfall_95"].value == pytest.approx((0.06 + 0.03) / 5)
    # Negative VaR: 4 losses of 2 % and 96 gains of 1 %; the tail holds the four losses and one
    # gain, and ES stays at or above VaR.
    t = tail_metrics(np.array([-0.02] * 4 + [0.01] * 96))
    assert t["var_loss_95"].value == pytest.approx(-0.01)
    assert t["expected_shortfall_95"].value == pytest.approx((0.08 - 0.01) / 5)


def test_expected_shortfall_fractional_tail_mass_on_small_samples() -> None:
    losses = np.arange(1, 22) / 100  # 0.01 .. 0.21; n = 21 gives a tail mass of 1.05
    es = tail_metrics(-losses)["expected_shortfall_95"]
    assert es.value == pytest.approx((0.21 + 0.05 * 0.20) / 1.05)
    assert es.extra["tail_observations"] == 2
    es20 = tail_metrics(-losses[:20])["expected_shortfall_95"]  # n = 20: a tail mass of one
    assert es20.value == pytest.approx(0.20)
    assert es20.extra["tail_observations"] == 1
    assert es20.extra["tail_mass"] == pytest.approx(1.0)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_expected_shortfall_is_at_least_var_and_is_the_worst_5_percent_mean(seed: int) -> None:
    rng = np.random.default_rng(seed)
    for n, flat_share in ((60, 0.0), (100, 0.9), (250, 0.5), (401, 0.0)):
        r = rng.normal(0.0, 0.01, n)
        r[rng.random(n) < flat_share] = 0.0
        t = tail_metrics(r)
        es, var = t["expected_shortfall_95"].value, t["var_loss_95"].value
        assert isinstance(es, float) and isinstance(var, float)
        assert es >= var - 1e-12
        if n % 20 == 0:  # an integer tail mass: the plain mean of the worst 5 % of losses
            worst = np.sort(-r)[::-1][: n // 20]
            assert es == pytest.approx(worst.mean())
            assert t["expected_shortfall_95"].extra["tail_observations"] == n // 20


def test_tail_metrics_rejects_a_level_outside_the_unit_interval() -> None:
    with pytest.raises(ValueError):
        tail_metrics(np.linspace(-0.05, 0.05, 30), level=1.0)


def test_expected_shortfall_at_another_level_has_no_rounding_residue() -> None:
    # (1 - 0.9) * 100 is 9.999999999999998 in floating point: the tail is still exactly the ten
    # largest losses, with no negative weight on an eleventh.
    losses = np.arange(1, 101) / 1000  # 0.001 .. 0.100
    es = tail_metrics(-losses, level=0.9)["expected_shortfall_95"]
    assert es.value == pytest.approx(np.mean(np.arange(91, 101) / 1000))
    assert es.extra["tail_observations"] == 10
    assert es.extra["tail_mass"] == pytest.approx(10.0)
    assert es.extra["tail_probability"] == pytest.approx(0.1)


def test_expected_shortfall_tail_mass_record_agrees_with_the_observation_count() -> None:
    # Review round 4: a remainder of 2e-9 on a whole part of 5000 is kept (one more observation
    # with weight), so the recorded mass must show it; 12 significant digits of the mass hid it.
    n = 100_000
    extra = tail_metrics(-np.arange(1, n + 1) / n, level=1 - (5000 + 2e-9) / n)[
        "expected_shortfall_95"
    ].extra
    mass = extra["tail_mass"]
    assert isinstance(mass, float)
    assert extra["tail_observations"] == 5001
    assert mass > 5000.0
    assert mass == pytest.approx(5000.000000002, abs=1e-11)


def test_expected_shortfall_with_a_tail_mass_below_the_tolerance_is_the_largest_loss() -> None:
    # Review round 3: a tail probability under 1e-9 / n leaves a remainder that is the whole
    # tail; it must stay, so the estimate is the largest loss, not a zero from an empty tail.
    losses = np.arange(1, 31) / 100
    es = tail_metrics(-losses, level=1 - 1e-12)["expected_shortfall_95"]
    assert es.value == pytest.approx(0.30)
    assert es.extra["tail_observations"] == 1
    assert es.status == "ok"


def test_tail_metrics_with_a_nan_return_stay_undefined_without_a_warning() -> None:
    r = np.linspace(-0.05, 0.05, 40)
    r[3] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t = tail_metrics(r)
    assert t["expected_shortfall_95"].to_dict()["status"] == "undefined"
    assert t["var_loss_95"].to_dict()["status"] == "undefined"


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


def test_per_side_win_rate_uses_the_flat_tolerance():
    """N4: a short trade that made 1e-9 is flat under the tolerance, not a win."""
    ep = pd.DataFrame(
        {
            "side": ["long", "long", "short", "short"],
            "pnl": [100.0, 1e-9, 1e-9, -30.0],
            "holding_sessions": [5, 3, 2, 4],
            "status": ["closed"] * 4,
        }
    )
    m = episode_metrics(ep, flat_tolerance=1e-6)
    assert m["win_rate"].value == pytest.approx(0.25)
    assert m["long_trades"].extra["win_rate"] == pytest.approx(0.5)
    assert m["short_trades"].extra["win_rate"] == pytest.approx(0.0)
