"""Bucket portfolios in evaluation hold exactly the names the mining diagnostics assign.

The two components never import each other; this cross-component test pins their shared
membership rule (average-rank percentiles, ties in one bucket, overlapping tails).
"""

import math
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.strategies import BucketStrategy, Slice
from invest_mining.diagnostics import assign_buckets, tail_masks, tail_returns


@pytest.mark.parametrize("seed", range(5))
def test_bucket_and_tail_membership_match_factor_diagnostics(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(10, 120))
    # Coarse scores force many ties; some names have no score.
    raw = rng.integers(0, max(3, n // 4), n).astype(float)
    raw[rng.random(n) < 0.1] = np.nan
    names = [f"S{i}" for i in range(n)]
    scores = pd.Series(raw, index=names)
    if scores.notna().sum() < 10:
        pytest.skip("too few scored names for ten buckets")
    expected = assign_buckets(scores.to_frame().T, 10).iloc[0]

    def held(long: Slice) -> set[str]:
        strategy = BucketStrategy(
            long, None, gross_leverage=1.0, min_names=1, min_names_per_bucket=1
        )
        return set(strategy.target_weights(scores).index)

    for k in range(1, 11):
        assert held(Slice("bucket", k, 10)) == set(expected.index[expected == k])
    for f in (0.01, 0.05, 0.07, 0.1, 0.25, 0.5):
        frame = scores.to_frame().T
        counts = tail_returns(frame, frame, (f,), min_names=1, min_cross_section=10)
        for side, mask in tail_masks(frame, f).items():
            members = set(mask.columns[mask.iloc[0]])
            assert held(Slice(side, f, 10)) == members
            assert len(members) == counts.loc[f"{side}_{float(f)}", "min_names"]


@pytest.mark.parametrize(
    ("n", "buckets"), [(25, 25), (125, 25), (250, 25), (101, 10), (87, 7), (129, 49)]
)
@pytest.mark.parametrize("ties", [False, True])
def test_bucket_members_match_exact_rational_ranks(n, buckets, ties):
    rng = np.random.default_rng(17)
    raw = rng.integers(0, max(3, n // 4), n) if ties else np.arange(n)
    scores = pd.Series(raw, index=[f"S{i}" for i in range(n)], dtype=float)
    # Keep missing scores in the input while deriving exact ranks from scored names.
    scores.loc["missing"] = np.nan
    expected = {}
    for name, value in scores.dropna().items():
        equal = int(scores.eq(value).sum())
        p = Fraction(2 * int(scores.lt(value).sum()) + equal + 1, 2 * n)
        q = Fraction(2 * int(scores.gt(value).sum()) + equal + 1, 2 * n)
        expected[name] = math.ceil(p * buckets) if p <= q else buckets + 1 - math.ceil(q * buckets)
    actual = assign_buckets(scores.to_frame().T, buckets).iloc[0]
    assert pd.isna(actual.loc["missing"])
    assert actual.dropna().astype(int).to_dict() == expected
    for k in range(1, buckets + 1):
        strategy = BucketStrategy(
            Slice("bucket", k, buckets),
            None,
            gross_leverage=1.0,
            min_names=1,
            min_names_per_bucket=1,
        )
        assert set(strategy.target_weights(scores).index) == {
            name for name, bucket in expected.items() if bucket == k
        }


def test_reversal_symmetry_does_not_require_equal_counts_with_unbalanced_ties():
    scores = pd.Series([*range(89), *[100.0] * 11], dtype=float)
    actual = assign_buckets(scores.to_frame().T, 10).iloc[0]
    reversed_ = assign_buckets((-scores).to_frame().T, 10).iloc[0]
    assert actual.eq(1).sum() == 10 and actual.eq(10).sum() == 11
    pd.testing.assert_series_equal(actual, 11 - reversed_)


def test_two_buckets_keep_the_median_in_the_partition_but_not_the_half_tails():
    scores = pd.Series([0.0, 1.0, 2.0], index=["low", "median", "high"])
    assert assign_buckets(scores.to_frame().T, 2).iloc[0].tolist() == [1, 2, 2]
    for slice_, expected in (
        (Slice("bucket", 2, 2), {"median", "high"}),
        (Slice("top", 0.5, 2), {"high"}),
        (Slice("bottom", 0.5, 2), {"low"}),
    ):
        strategy = BucketStrategy(
            slice_, None, gross_leverage=1, min_names=1, min_names_per_bucket=1
        )
        assert set(strategy.target_weights(scores).index) == expected
