"""Backtest configuration. Every assumption that changes results is an explicit field."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CostModel:
    """Per-trade costs, charged in cash on top of fills at the (mid) open price.

    cost = notional * (commission_bps + half_spread_bps) / 1e4
         + notional * impact_coef * daily_vol * sqrt(notional / adv_dollar)

    The last term is the square-root market-impact law (impact grows with the square
    root of participation, scaled by volatility). ``daily_vol`` and ``adv_dollar`` are
    trailing estimates known at the decision date. Shorts pay ``borrow_bps_annual`` on
    their market value each session; cash earns (or, if negative, pays)
    ``cash_rate_annual``.
    """

    commission_bps: float = 1.0
    half_spread_bps: float = 5.0
    impact_coef: float = 0.5
    borrow_bps_annual: float = 50.0
    cash_rate_annual: float = 0.0
    adv_window: int = 20
    vol_window: int = 20

    def scaled(self, multiplier: float) -> CostModel:
        """Scale every transaction-cost and borrow parameter (stress scenarios)."""
        return replace(
            self,
            commission_bps=self.commission_bps * multiplier,
            half_spread_bps=self.half_spread_bps * multiplier,
            impact_coef=self.impact_coef * multiplier,
            borrow_bps_annual=self.borrow_bps_annual * multiplier,
        )


@dataclass(frozen=True)
class StrategyConfig:
    """Quantile portfolio: long the top ``long_fraction``, short the bottom ``short_fraction``.

    ``short_fraction = 0`` gives a long-only portfolio. Weights are equal within each leg
    and sum to ``gross_leverage`` in absolute value (split evenly between legs).
    """

    long_fraction: float = 0.1
    short_fraction: float = 0.1
    gross_leverage: float = 1.0
    rebalance_every: int = 5
    min_names: int = 10


@dataclass(frozen=True)
class ExecutionConfig:
    """Timing and tradability.

    A decision uses signals and prices through the close of decision date ``t``; orders
    fill at the open of ``t + 1 + delay``. An order for an instrument with no bar on the
    fill date is rejected. Each fill is capped at ``max_participation`` of trailing
    average dollar volume; the unfilled remainder is dropped (and reported).
    """

    delay: int = 0
    max_participation: float = 0.05
    min_price: float = 1.0
    min_adv_dollar: float = 0.0


@dataclass(frozen=True)
class BacktestConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    costs: CostModel = field(default_factory=CostModel)
    initial_capital: float = 1_000_000.0
    annualization: int = 252
    risk_free_annual: float = 0.0
    mar_annual: float = 0.0
    start: str | None = None
    end: str | None = None

    def __post_init__(self) -> None:
        s, e = self.strategy, self.execution
        if not (0 < s.long_fraction <= 1 and 0 <= s.short_fraction <= 1):
            raise ValueError("long_fraction must be in (0, 1], short_fraction in [0, 1]")
        if s.long_fraction + s.short_fraction > 1:
            raise ValueError("long and short legs overlap")
        if s.rebalance_every < 1 or e.delay < 0 or not 0 < e.max_participation <= 1:
            raise ValueError("invalid rebalance_every / delay / max_participation")
        if self.initial_capital <= 0 or s.gross_leverage <= 0:
            raise ValueError("initial_capital and gross_leverage must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> BacktestConfig:
        known = {f.name for f in fields(BacktestConfig)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown config keys {sorted(unknown)}")

        def sub(cls: type, key: str) -> Any:
            data = raw.get(key, {})
            bad = set(data) - {f.name for f in fields(cls)}
            if bad:
                raise ValueError(f"unknown {key} keys {sorted(bad)}")
            return cls(**data)

        top = {k: v for k, v in raw.items() if k not in ("strategy", "execution", "costs")}
        return BacktestConfig(
            strategy=sub(StrategyConfig, "strategy"),
            execution=sub(ExecutionConfig, "execution"),
            costs=sub(CostModel, "costs"),
            **top,
        )

    @staticmethod
    def load(path: str | os.PathLike[str]) -> BacktestConfig:
        return BacktestConfig.from_dict(json.loads(Path(path).read_text()))
