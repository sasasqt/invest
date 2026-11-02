import numpy as np
import pandas as pd
import pytest

from invest_mining import reporting
from invest_mining.diagnostics import quantile_returns, quantile_summary, tail_returns
from invest_mining.reporting import staggered_spread_wealth, write_factor_report


def test_staggered_spread_compounds_each_day_once_not_horizon_times():
    """K2: overlapping h-day spreads compounded daily count every day h times."""
    dates = pd.bdate_range("2024-01-01", periods=30)
    spread = pd.Series(0.03, index=dates)  # 1% a day held for 3 days
    wealth = staggered_spread_wealth(spread, 3)
    assert wealth.iloc[-1] == pytest.approx(1.03**10)  # each cohort trades ten times
    assert staggered_spread_wealth(spread, 1).iloc[-1] == pytest.approx(1.03**30)


def test_staggered_spread_holds_cash_and_shows_undefined_dates_as_gaps():
    dates = pd.bdate_range("2024-01-01", periods=4)
    spread = pd.Series([0.02, np.nan, 0.04, 0.0], index=dates)
    wealth = staggered_spread_wealth(spread, 2)
    assert np.isnan(wealth.iloc[1])
    # Cohort 0 trades dates 0 and 2; cohort 1 holds cash on date 1, then trades date 3.
    assert wealth.iloc[-1] == pytest.approx((1.02 * 1.04 + 1.0) / 2)
    for horizon in (0, True, 1.5):
        with pytest.raises(ValueError, match="horizon must be a positive integer"):
            staggered_spread_wealth(spread, horizon)


def test_factor_figures_draw_no_zeros_for_undefined_ic_or_insufficient_buckets(
    tmp_path, monkeypatch
):
    """S3-1 and K7: undefined values are gaps or labels in the figures, never zeros."""
    dates = pd.bdate_range("2024-01-01", periods=6)
    f = pd.DataFrame([range(100)] * 6, index=dates, dtype=float)
    y = f / 1000
    y.iloc[:, 91:] = np.nan  # top decile: one observed name, so no mean
    ic = pd.DataFrame({"ic": [0.1, np.nan, 0.2, 0.1, np.nan, 0.3], "n": 100}, index=dates)
    figures = []
    monkeypatch.setattr(reporting.plt, "close", figures.append)
    write_factor_report(
        tmp_path / "report",
        expression="close",
        summary={"mean_ic": 0.1},
        ic=ic,
        quantiles=quantile_returns(f, y, 10, min_names=5),
        quantile_summary=quantile_summary(f, y, 10, min_names=5),
        tails=tail_returns(f, y),
        config={"horizon": 2},
    )
    ic_figure, quantile_figure = figures
    cumulative = ic_figure.axes[1].lines[0].get_ydata()
    np.testing.assert_allclose(cumulative, [0.1, np.nan, 0.3, 0.4, np.nan, 0.7])
    bars, wealth = quantile_figure.axes
    assert [round(p.get_x() + p.get_width() / 2) for p in bars.patches] == list(range(1, 10))
    assert any("insufficient" in t.get_text() for t in bars.texts)
    assert np.isnan(wealth.lines[0].get_ydata()).all()  # no defined top-minus-bottom date
