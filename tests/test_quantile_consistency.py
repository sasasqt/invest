"""Bucket portfolios in evaluation hold exactly the names the mining diagnostics assign.

The two components never import each other; this cross-component test pins their shared
membership rule (average-rank percentiles, ties in one bucket, overlapping tails).
"""

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.strategies import BucketStrategy, Slice
from invest_mining.diagnostics import assign_buckets, tail_returns


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
    for f in (0.01, 0.05, 0.1, 0.25):
        counts = tail_returns(
            scores.to_frame().T, scores.to_frame().T, (f,), min_names=1, min_cross_section=10
        )["min_names"]
        for side in ("top", "bottom"):
            assert len(held(Slice(side, f, 10))) == counts[f"{side}_{f:g}"]
