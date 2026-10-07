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


def percentile_ranks(scores: pd.Series) -> pd.Series:
    """Average-rank percentiles in (0, 1]; tied scores share one percentile.

    The same rule as the factor diagnostics in ``invest_mining.diagnostics``, so bucket
    portfolios hold exactly the names the diagnostics assign to that bucket.
    """
    return scores.rank(method="average", pct=True)


@dataclass(frozen=True)
class Slice:
    """A set of names selected by their decision-time percentile ``p``.

    * ``bucket``: bucket ``value`` of ``n_buckets`` equal-width percentile buckets, i.e.
      ``ceil(p * n_buckets) == value`` (bucket 1 holds the lowest scores).
    * ``top``: ``p > 1 - value``; ``bottom``: ``p <= value`` (overlapping tail slices).

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
        return f"{self.kind}_{self.value:g}"

    def mask(self, pct: pd.Series) -> pd.Series:
        if self.kind == "bucket":
            bucket = np.ceil(pct * self.n_buckets).clip(lower=1, upper=self.n_buckets)
            return bucket == int(self.value)
        if self.kind == "top":
            return pct > 1 - self.value
        return pct <= self.value


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
        longs = scores.index[self.long.mask(pct).to_numpy()]
        shorts = (
            scores.index[self.short.mask(pct).to_numpy()]
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
