import math

import numpy as np
import pandas as pd
import pytest

from invest_mining.diagnostics import (
    assign_buckets,
    benjamini_hochberg,
    daily_ic,
    forward_returns,
    holm_adjust,
    newey_west_mean_test,
    quantile_returns,
    tail_returns,
)


def test_forward_returns_alignment():
    idx = pd.bdate_range("2024-01-01", periods=5)
    open_ = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=idx)
    fr = forward_returns(open_, 2)
    # Decision on day 0 -> enter at open of day 1 (11) -> exit at open of day 3 (13).
    assert fr["A"].iloc[0] == pytest.approx(13 / 11 - 1)
    assert fr["A"].iloc[1] == pytest.approx(14 / 12 - 1)
    assert fr["A"].iloc[2:].isna().all()


def test_daily_ic_matches_pandas_and_handles_degenerate_dates():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=4)
    cols = list("ABCDEFG")
    f = pd.DataFrame(rng.normal(size=(4, 7)), index=idx, columns=cols)
    y = pd.DataFrame(rng.normal(size=(4, 7)), index=idx, columns=cols)
    f.iloc[1] = 1.0  # constant factor -> undefined
    y.iloc[2, :4] = np.nan  # only 3 pairs -> insufficient
    out = daily_ic(f, y, "pearson")
    assert out["ic"].iloc[0] == pytest.approx(f.iloc[0].corr(y.iloc[0]))
    assert math.isnan(out["ic"].iloc[1]) and math.isnan(out["ic"].iloc[2])
    sp = daily_ic(f, y, "spearman")
    assert sp["ic"].iloc[3] == pytest.approx(f.iloc[3].rank().corr(y.iloc[3].rank()))
    assert out["n"].tolist() == [7, 7, 3, 7]


def test_newey_west_lag_zero_equals_iid_and_hand_lag_one():
    x = np.array([0.1, -0.2, 0.3, 0.05, -0.1, 0.2] * 6)
    n = len(x)
    t0 = newey_west_mean_test(x, lags=0)
    assert t0.se == pytest.approx(x.std(ddof=0) / math.sqrt(n))
    e = x - x.mean()
    lr = (e @ e) / n + 2 * 0.5 * (e[1:] @ e[:-1]) / n
    assert newey_west_mean_test(x, lags=1).se == pytest.approx(math.sqrt(lr / n))
    assert newey_west_mean_test(x[:10], lags=1).status == "insufficient_data"
    assert newey_west_mean_test(np.zeros(40), lags=1).status == "undefined"


def test_multiple_testing_adjustments():
    p = [0.01, 0.04, 0.03, 0.005]
    assert holm_adjust(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert benjamini_hochberg(p) == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_buckets_keep_ties_and_require_enough_names():
    idx = pd.bdate_range("2024-01-01", periods=2)
    f = pd.DataFrame(
        [[1, 2, 3, 4, 4], [1, 2, np.nan, np.nan, np.nan]],
        index=idx,
        columns=list("ABCDE"),
        dtype=float,
    )
    b = assign_buckets(f, 5)
    assert b.iloc[0].tolist() == [1, 2, 3, 5, 5]
    assert b.iloc[1].isna().all()


def test_quantile_and_tail_returns_on_monotone_signal():
    idx = pd.bdate_range("2024-01-01", periods=3)
    cols = [f"S{i}" for i in range(20)]
    f = pd.DataFrame([list(range(20))] * 3, index=idx, columns=cols, dtype=float)
    y = f / 100.0
    q = quantile_returns(f, y, 10)
    assert (q.mean().diff().dropna() > 0).all()
    t = tail_returns(f, y, (0.1,), min_names=1)
    assert t.loc["top_0.1", "mean_forward_return"] == pytest.approx(0.185)
    assert t.loc["bottom_0.1", "mean_forward_return"] == pytest.approx(0.005)


@pytest.mark.parametrize("drop_column", [False, True])
def test_quantiles_and_tails_do_not_use_future_label_availability(drop_column):
    f = pd.DataFrame([range(1, 11)], columns=list("ABCDEFGHIJ"), dtype=float)
    y = f / 100
    baseline = quantile_returns(f, y)
    changed = y.drop(columns="J") if drop_column else y.assign(J=np.nan)
    altered = quantile_returns(f, changed)
    pd.testing.assert_frame_equal(baseline.iloc[:, :9], altered.iloc[:, :9])
    assert len(altered) == 1 and altered["q10"].isna().all()
    tails = tail_returns(f, changed, (0.1,), min_names=1)
    assert pd.isna(tails.loc["top_0.1", "mean_forward_return"])
    assert tails.loc["bottom_0.1", "mean_forward_return"] == pytest.approx(0.01)


def test_quantile_dates_are_preserved_when_all_future_labels_are_missing():
    f = pd.DataFrame([range(10)], columns=list("ABCDEFGHIJ"), dtype=float)
    result = quantile_returns(f, f * np.nan)
    assert result.index.equals(f.index) and result.isna().all().all()


def test_tail_slices_report_small_samples_instead_of_a_mean():
    idx = pd.bdate_range("2024-01-01", periods=2)
    f = pd.DataFrame([list(range(40))] * 2, index=idx, columns=[f"S{i}" for i in range(40)])
    f = f.astype(float)
    t = tail_returns(f, f / 100, (0.05, 0.1), min_names=3)
    assert t.loc["top_0.05", "status"] == "insufficient_data"  # 2 names per date
    assert pd.isna(t.loc["top_0.05", "mean_forward_return"])
    assert t.loc["top_0.05", "min_names"] == 2 and t.loc["top_0.05", "insufficient_dates"] == 2
    assert t.loc["top_0.1", "status"] == "ok" and t.loc["top_0.1", "min_names"] == 4
    assert t.loc["top_0.1", "mean_forward_return"] == pytest.approx(0.375)


def test_tail_ties_stay_together_and_small_cross_sections_are_skipped():
    f = pd.DataFrame(
        [[1.0] * 6 + [2.0] * 6, [*range(5), *[np.nan] * 7]],
        index=pd.bdate_range("2024-01-01", periods=2),
        columns=[f"S{i}" for i in range(12)],
    )
    t = tail_returns(f, f, (0.5,), min_names=1, min_cross_section=10)
    # Day 1: the six tied 2.0s all sit above the median; day 2 has too few names.
    assert t.loc["top_0.5", "min_names"] == 6 and t.loc["bottom_0.5", "min_names"] == 6
    assert t.loc["top_0.5", "n_dates"] == 1
