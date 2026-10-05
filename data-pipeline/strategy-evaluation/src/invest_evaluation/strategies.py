"""Trading rules: map decision-time scores to target portfolio weights.

A strategy sees only the scores of instruments that are eligible at the decision date
(the engine filters by tradability and liquidity). It never sees prices after the
decision date, fills, or costs; the engine owns execution and accounting.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from invest_evaluation.config import StrategyConfig


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
        longs = names[n - n_long :]
        shorts = names[:n_short]
        leg = cfg.gross_leverage / (2 if n_short else 1)
        weights = {k: leg / n_long for k in longs}
        weights.update({k: -leg / n_short for k in shorts})
        return pd.Series(weights, dtype=float)
