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
    tail_masks,
    tail_percentiles,
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
    # The tied top pair has average rank 4.5 (q = 0.3), the mirror of a tied bottom pair
    # (p = 0.3, bucket 2), so it shares bucket 4 and bucket 5 stays empty.
    assert b.iloc[0].tolist() == [1, 2, 3, 4, 4]
    assert b.iloc[1].isna().all()
    mirrored = assign_buckets(-f, 5)
    assert mirrored.iloc[0].tolist() == [5, 4, 3, 2, 2]


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


@pytest.mark.parametrize("observed", [0, 1, 4])
def test_tail_status_requires_observed_outcomes_without_changing_membership(observed):
    f = pd.DataFrame([range(100)], dtype=float)
    y = f / 100
    y.loc[:, 90:] = np.nan
    if observed:
        y.loc[:, 100 - observed :] = 0.5
    baseline = tail_returns(f, f / 100, (0.1,))
    tails = tail_returns(f, y, (0.1,))
    top = tails.loc["top_0.1"]
    assert top["status"] == "insufficient_data"
    assert pd.isna(top["mean_forward_return"]) and top["n_dates"] == 0
    assert top["min_names"] == baseline.loc["top_0.1", "min_names"] == 10
    assert top["min_observed_names"] == observed and top["insufficient_label_dates"] == 1
    assert tails.loc["bottom_0.1", "status"] == "ok"


def test_tail_with_no_observable_dates_is_insufficient():
    f = pd.DataFrame([range(100)], dtype=float)
    tails = tail_returns(f, f * np.nan, (0.1,))
    assert (tails["status"] == "insufficient_data").all()
    assert tails["mean_forward_return"].isna().all() and tails["n_dates"].eq(0).all()


def test_tail_coverage_reports_unavailable_horizon_end_and_enough_observed_names():
    f = pd.DataFrame([range(100)] * 2, dtype=float)
    y = f / 100
    y.iloc[0, 90:95] = np.nan  # Five observed names still meet the declared minimum.
    y.iloc[1, :] = np.nan  # The final date has no observable forward outcomes anywhere.
    tails = tail_returns(f, y, (0.1,))
    top = tails.loc["top_0.1"]
    assert top["status"] == "ok" and top["n_dates"] == 1
    assert top["min_names"] == 10 and top["min_observed_names"] == 5
    assert top["missing_label_dates"] == 1 and top["insufficient_label_dates"] == 0
    assert top["mean_forward_return"] == pytest.approx(0.97)


def test_close_tail_fractions_keep_distinct_diagnostic_rows():
    f = pd.DataFrame([range(100)], dtype=float)
    tails = tail_returns(f, f / 100, (0.1, 0.10000001))
    assert len(tails) == 4 and tails.index.is_unique
    # Both fractions select ten names on each side: q <= f is exact, not 1 - f rounding.
    assert (tails["min_names"] == 10).all()


@pytest.mark.parametrize("field", ["min_names", "min_cross_section"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_tail_minimum_counts_must_be_positive_integers(field, value):
    f = pd.DataFrame([range(100)], dtype=float)
    with pytest.raises(ValueError, match=f"{field} must be a positive integer"):
        tail_returns(f, f / 100, (0.1,), **{field: value})


@pytest.mark.parametrize(("n", "f", "count"), [(100, 0.07, 7), (250, 0.01, 2), (250, 0.05, 12)])
def test_top_and_bottom_tails_hold_the_same_number_of_names(n, f, count):
    f_ = pd.DataFrame([range(n)], dtype=float)
    tails = tail_returns(f_, f_ / 100, (f,), min_names=1)
    assert (tails["min_names"] == count).all()
    masks = tail_masks(f_, f)
    assert list(masks["top"].columns[masks["top"].iloc[0]]) == list(range(n - count, n))


def test_deciles_mirror_and_end_deciles_equal_the_ten_percent_tails():
    rng = np.random.default_rng(1)
    f_ = pd.DataFrame(rng.integers(0, 30, (40, 120)), dtype=float)
    f_ = f_.mask(rng.random(f_.shape) < 0.2)
    b, reversed_ = assign_buckets(f_, 10), assign_buckets(-f_, 10)
    masks = tail_masks(f_, 0.1)
    pd.testing.assert_frame_equal(b.eq(1), masks["bottom"])
    pd.testing.assert_frame_equal(b.eq(10), masks["top"])
    pct = tail_percentiles(f_)
    off_median = pct["bottom"] != pct["top"]  # an exact median is not mirrored
    assert (reversed_ == 11 - b)[off_median & f_.notna()].all().all()
    counts = pd.Series(range(28), dtype=float).to_frame().T
    assert assign_buckets(counts, 10).iloc[0].value_counts().sort_index().tolist() == [
        2, 3, 3, 3, 3, 3, 3, 3, 3, 2,
    ]  # fmt: skip


def test_top_tail_is_the_bottom_tail_of_reversed_scores():
    rng = np.random.default_rng(0)
    f_ = pd.DataFrame(rng.integers(0, 20, (30, 150)), dtype=float)
    f_ = f_.mask(rng.random(f_.shape) < 0.1)
    for frac in (0.01, 0.05, 0.07, 0.1, 0.5):
        masks, reversed_ = tail_masks(f_, frac), tail_masks(-f_, frac)
        pd.testing.assert_frame_equal(masks["top"], reversed_["bottom"])
        assert not (masks["top"] & masks["bottom"]).any().any()


def test_minimum_cross_section_applies_to_deciles():
    f_ = pd.DataFrame([range(12), [*range(10), np.nan, np.nan]], dtype=float)
    assert assign_buckets(f_, 10).notna().any(axis=1).tolist() == [True, True]
    assert assign_buckets(f_, 10, 11).notna().any(axis=1).tolist() == [True, False]
    q = quantile_returns(f_, f_, 10, 11)
    assert q.iloc[0].notna().all() and q.iloc[1].isna().all()
    with pytest.raises(ValueError):
        assign_buckets(f_, 10, 0)


def test_deciles_and_tails_use_the_same_dates():
    f_ = pd.DataFrame([range(12), [*range(10), np.nan, np.nan], [*range(5), *[np.nan] * 7]])
    f_ = f_.astype(float)
    for minimum in (1, 11):
        deciles = quantile_returns(f_, f_, 10, minimum)
        tails = tail_returns(f_, f_, (0.5,), min_names=1, min_cross_section=minimum)
        assert tails["n_dates"].eq(deciles.notna().any(axis=1).sum()).all()


@pytest.mark.parametrize("n", [25, 125, 250])
def test_bucket_boundaries_do_not_round_exact_ranks_into_the_next_bucket(n):
    # Integer arithmetic is an independent oracle for distinct ranks. In particular,
    # rank / n = 0.28 is an exact seventh boundary of 25 buckets, not bucket eight.
    ranks = np.arange(1, n + 1)
    descending = ranks[::-1]
    expected = np.where(
        ranks <= descending,
        (ranks * 25 + n - 1) // n,
        26 - (descending * 25 + n - 1) // n,
    )
    factor = pd.DataFrame([range(n)], dtype=float)
    np.testing.assert_array_equal(assign_buckets(factor, 25).iloc[0], expected)
