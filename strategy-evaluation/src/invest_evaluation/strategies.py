"""Trading rules: map decision-time scores to target portfolio weights.

A strategy sees only the scores of instruments that are eligible at the decision date
(the engine filters by tradability and liquidity). It never sees prices after the
decision date, fills, or costs; the engine owns execution and accounting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Protocol

import numpy as np
import pandas as pd

from invest_evaluation.config import StrategyConfig

SLICE_KINDS = ("bucket", "top", "bottom")


class Strategy(Protocol):
    def target_weights(self, scores: pd.Series) -> pd.Series:
        """Return target weights (fraction of equity) indexed by instrument."""
        ...


class QuantileStrategy:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def target_weights(self, scores: pd.Series) -> pd.Series:
        cfg = self.config
        scores = scores.dropna()
        n = len(scores)
        if n < cfg.min_names:
            return pd.Series(dtype=float)
        # Deterministic tie-break by instrument id so results don't depend on input order.
        ranked = sorted(scores.items(), key=lambda kv: (kv[1], str(kv[0])))
        names = [k for k, _ in ranked]
        n_long = max(1, int(np.floor(n * cfg.long_fraction)))
        n_short = int(np.floor(n * cfg.short_fraction))
        if cfg.short_fraction > 0:
            n_short = max(1, n_short)
        if n_long + n_short > n:
            return pd.Series(dtype=float)  # too few names for disjoint long/short legs
        longs = names[n - n_long :]
        shorts = names[:n_short]
        leg = cfg.gross_leverage / (2 if n_short else 1)
        weights = {k: leg / n_long for k in longs}
        weights.update({k: -leg / n_short for k in shorts})
        return pd.Series(weights, dtype=float)


def percentile_ranks(scores: pd.Series, *, descending: bool = False) -> pd.Series:
    """Average-rank percentiles in (0, 1]; tied scores share one percentile.

    ``descending=True`` ranks from the highest score down, so the top tail uses the same
    exact ``rank / n <= f`` comparison as the bottom tail. The same rule as the factor
    diagnostics in ``invest_mining.diagnostics``, so bucket portfolios hold exactly the
    names the diagnostics assign to that bucket.
    """
    return scores.rank(method="average", pct=True, ascending=not descending)


def bucket_numbers(pct: pd.Series, pct_from_top: pd.Series, n_buckets: int) -> pd.Series:
    """Symmetric percentile buckets 1..n (the factor diagnostics' rule).

    Names in the lower half (``p <= q``) get ``ceil(p * n)``; names in the upper half get
    ``n + 1 - ceil(q * n)``. For at least three buckets the extremes equal the ``1/n``
    tails. Ties can give the two extremes different populations. A name or tie group
    exactly at the median (``p == q``) gets ``ceil(p * n)`` whichever way the scores
    point, so it is the one placement that is not mirrored.
    """
    # Compare with the cutpoints themselves: ceil(0.28 * 25) can incorrectly be eight.
    # side="left" keeps a percentile exactly on k/n in bucket k, as with tail p <= f.
    cutpoints = np.arange(1, n_buckets + 1) / n_buckets

    def from_percentiles(values: pd.Series) -> pd.Series:
        numbers = np.searchsorted(cutpoints, values.to_numpy(), side="left") + 1
        return pd.Series(numbers, index=values.index, name=values.name, dtype=float).where(
            values.notna()
        )

    lower = from_percentiles(pct)
    upper = n_buckets + 1 - from_percentiles(pct_from_top)
    return lower.where(pct <= pct_from_top, upper).clip(lower=1, upper=n_buckets)


@dataclass(frozen=True)
class Slice:
    """A set of names selected by their decision-time percentile ``p``.

    * ``bucket``: bucket ``value`` of ``n_buckets`` symmetric percentile buckets
      (``bucket_numbers``; bucket 1 holds the lowest scores).
    * ``bottom``: ``p <= value``; ``top``: ``q <= value``, where ``q`` is the same
      percentile counted from the highest score (overlapping tail slices). The two tails
      are mirror images: reversing the scores swaps their members.

    Ties share a percentile, so they always fall in the same slice; populations can be
    unequal or empty, and are reported instead of being rebalanced by instrument id.
    """

    kind: str
    value: float
    n_buckets: int = 10

    def __post_init__(self) -> None:
        if self.kind not in SLICE_KINDS:
            raise ValueError(f"slice kind must be one of {SLICE_KINDS}")
        if (
            isinstance(self.n_buckets, bool)
            or not isinstance(self.n_buckets, Integral)
            or self.n_buckets < 2
        ):
            raise ValueError("n_buckets must be an integer >= 2")
        v = self.value
        if isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v):
            raise ValueError("slice value must be a finite number")
        if self.kind == "bucket":
            if v != int(v) or not 1 <= v <= self.n_buckets:
                raise ValueError("bucket must be an integer in 1..n_buckets")
        elif not 0 < v <= 0.5:
            raise ValueError("tail fraction must be in (0, 0.5]")

    @property
    def label(self) -> str:
        if self.kind == "bucket":
            return f"q{int(self.value)}"
        # Float's shortest round-trip representation keeps distinct fractions distinct.
        return f"{self.kind}_{float(self.value)}"

    def mask(self, pct: pd.Series, pct_from_top: pd.Series) -> pd.Series:
        """Members given ascending (``pct``) and descending (``pct_from_top``) percentiles."""
        if self.kind == "bottom":
            return pct <= self.value
        if self.kind == "top":
            return pct_from_top <= self.value
        return bucket_numbers(pct, pct_from_top, self.n_buckets) == int(self.value)


class BucketStrategy:
    """Equal-weight portfolio of one percentile slice, or long one slice and short another.

    Decisions with fewer eligible names than ``max(min_names, n_buckets)`` hold nothing,
    as the factor diagnostics skip dates with fewer names than buckets. A leg with fewer
    than ``min_names_per_bucket`` names also holds nothing for that decision rather than
    concentrating in one or two stocks; callers report such decisions as insufficient.
    """

    def __init__(
        self,
        long: Slice,
        short: Slice | None,
        *,
        gross_leverage: float,
        min_names: int,
        min_names_per_bucket: int,
    ) -> None:
        if short is not None and short.n_buckets != long.n_buckets:
            raise ValueError("long and short slices must use the same n_buckets")
        self.long, self.short = long, short
        self.gross_leverage = gross_leverage
        self.min_cross_section = max(min_names, long.n_buckets)
        self.min_names_per_bucket = min_names_per_bucket

    def target_weights(self, scores: pd.Series) -> pd.Series:
        scores = scores.dropna()
        if len(scores) < self.min_cross_section:
            return pd.Series(dtype=float)
        pct = percentile_ranks(scores)
        pct_from_top = percentile_ranks(scores, descending=True)
        longs = scores.index[self.long.mask(pct, pct_from_top).to_numpy()]
        shorts = (
            scores.index[self.short.mask(pct, pct_from_top).to_numpy()]
            if self.short is not None
            else pd.Index([])
        )
        legs = [longs] if self.short is None else [longs, shorts]
        if any(len(leg) < self.min_names_per_bucket for leg in legs):
            return pd.Series(dtype=float)
        if longs.intersection(shorts).size:
            raise ValueError("long and short slices overlap")
        leg_weight = self.gross_leverage / len(legs)
        weights = {k: leg_weight / len(longs) for k in longs}
        weights.update({k: -leg_weight / len(shorts) for k in shorts})
        return pd.Series(weights, dtype=float)
