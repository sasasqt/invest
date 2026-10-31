"""Backtest configuration. Every assumption that changes results is an explicit field."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date
from numbers import Integral, Real
from pathlib import Path
from typing import Any


def _number(name: str, value: Any, *, minimum: float | None = None, strict: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and (value <= minimum if strict else value < minimum):
        relation = ">" if strict else ">="
        raise ValueError(f"{name} must be {relation} {minimum}")


def _integer(name: str, value: Any, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


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

    def __post_init__(self) -> None:
        for name in ("commission_bps", "half_spread_bps", "impact_coef", "borrow_bps_annual"):
            _number(name, getattr(self, name), minimum=0)
        _number("cash_rate_annual", self.cash_rate_annual, minimum=-1, strict=True)
        _integer("adv_window", self.adv_window, 1)
        _integer("vol_window", self.vol_window, 2)

    def scaled(self, multiplier: float) -> CostModel:
        """Scale every transaction-cost and borrow parameter (stress scenarios)."""
        _number("cost multiplier", multiplier, minimum=0)
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

    def __post_init__(self) -> None:
        _number("long_fraction", self.long_fraction, minimum=0, strict=True)
        _number("short_fraction", self.short_fraction, minimum=0)
        if self.long_fraction + self.short_fraction > 1:
            raise ValueError("long and short fractions must sum to <= 1")
        _number("gross_leverage", self.gross_leverage, minimum=0, strict=True)
        _integer("rebalance_every", self.rebalance_every, 1)
        _integer("min_names", self.min_names, 1)


@dataclass(frozen=True)
class ExecutionConfig:
    """Timing and tradability.

    A decision uses signals and prices through the close of decision date ``t``; orders
    fill at the open of ``t + 1 + delay``. An order for an instrument with no bar on the
    fill date is rejected. Each fill is capped at ``max_participation`` of trailing
    average dollar volume; the unfilled remainder is dropped (and reported). A name is
    eligible at a decision only with a close, a trailing ADV above ``min_adv_dollar`` and
    a trailing volatility (the cost model's complete windows); the exit of a name whose
    windows a missing bar interrupted uses the bars and daily returns they still hold, or
    the complete estimate from just before the gap when a window is too short for that.
    """

    delay: int = 0
    max_participation: float = 0.05
    min_price: float = 1.0
    min_adv_dollar: float = 0.0

    def __post_init__(self) -> None:
        _integer("delay", self.delay, 0)
        _number("max_participation", self.max_participation, minimum=0, strict=True)
        if self.max_participation > 1:
            raise ValueError("max_participation must be <= 1")
        _number("min_price", self.min_price, minimum=0)
        _number("min_adv_dollar", self.min_adv_dollar, minimum=0)


VALIDATION_BENCHMARKS = ("none", "universe", "external")


@dataclass(frozen=True)
class ValidationConfig:
    """Rules for the portfolio verdict, declared before the run (ROBUST-02).

    Solvency and a valid base net Sharpe are mandatory. Known insolvency is ``rejected``
    regardless of sample size or optional rules. A portfolio is ``supported`` only if
    the net Sharpe bootstrap interval lies above zero,
    the deflated Sharpe ratio reaches ``min_deflated_sharpe``, every named stress scenario
    keeps a positive net Sharpe and, unless ``benchmark = "none"``, the information ratio
    against that benchmark is positive. It is ``rejected`` when the interval lies below
    zero and ``insufficient_data`` with fewer than ``min_sessions`` daily returns or no
    defined interval. Everything else is ``inconclusive``.
    """

    min_sessions: int = 252
    min_deflated_sharpe: float = 0.95
    stress_scenarios: tuple[str, ...] = ("costs_x2", "delay_1")
    benchmark: str = "none"

    def __post_init__(self) -> None:
        _integer("min_sessions", self.min_sessions, 60)
        _number("min_deflated_sharpe", self.min_deflated_sharpe, minimum=0)
        if self.min_deflated_sharpe > 1:
            raise ValueError("min_deflated_sharpe must be <= 1")
        names = self.stress_scenarios
        if isinstance(names, str) or not isinstance(names, list | tuple):
            raise ValueError("stress_scenarios must be a list of scenario names")
        if not all(isinstance(n, str) and n for n in names) or len(set(names)) != len(names):
            raise ValueError("stress_scenarios must be unique non-empty names")
        object.__setattr__(self, "stress_scenarios", tuple(names))
        if self.benchmark not in VALIDATION_BENCHMARKS:
            raise ValueError(f"benchmark must be one of {VALIDATION_BENCHMARKS}")


@dataclass(frozen=True)
class BacktestConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    costs: CostModel = field(default_factory=CostModel)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    initial_capital: float = 1_000_000.0
    annualization: int = 252
    risk_free_annual: float = 0.0
    mar_annual: float = 0.0
    start: str | None = None
    end: str | None = None

    def __post_init__(self) -> None:
        for name, cls in (
            ("strategy", StrategyConfig),
            ("execution", ExecutionConfig),
            ("costs", CostModel),
            ("validation", ValidationConfig),
        ):
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f"{name} must be a {cls.__name__}")
        _number("initial_capital", self.initial_capital, minimum=0, strict=True)
        _integer("annualization", self.annualization, 1)
        _number("risk_free_annual", self.risk_free_annual, minimum=-1, strict=True)
        _number("mar_annual", self.mar_annual, minimum=-1, strict=True)
        for name in ("start", "end"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"{name} must be an ISO date string")
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError
                except ValueError as exc:
                    raise ValueError(f"{name} must be an ISO date string (YYYY-MM-DD)") from exc
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must be <= end")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> BacktestConfig:
        if not isinstance(raw, dict):
            raise ValueError("config must be a JSON object")
        known = {f.name for f in fields(BacktestConfig)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown config keys {sorted(unknown)}")

        def sub(cls: type, key: str) -> Any:
            data = raw.get(key, {})
            if not isinstance(data, dict):
                raise ValueError(f"{key} must be a JSON object")
            bad = set(data) - {f.name for f in fields(cls)}
            if bad:
                raise ValueError(f"unknown {key} keys {sorted(bad)}")
            return cls(**data)

        nested = ("strategy", "execution", "costs", "validation")
        top = {k: v for k, v in raw.items() if k not in nested}
        return BacktestConfig(
            strategy=sub(StrategyConfig, "strategy"),
            execution=sub(ExecutionConfig, "execution"),
            costs=sub(CostModel, "costs"),
            validation=sub(ValidationConfig, "validation"),
            **top,
        )

    @staticmethod
    def load(path: str | os.PathLike[str]) -> BacktestConfig:
        return BacktestConfig.from_dict(json.loads(Path(path).read_text()))
