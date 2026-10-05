"""Stress scenarios for a *fixed* strategy: costs, execution delay, rebalance frequency.

Scenarios vary assumptions, never the signal or the trading rule's thresholds, and every
scenario is reported (not only the best).
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.metrics import compute_metrics

DEFAULT_SCENARIOS: dict[str, dict[str, float]] = {
    "base": {},
    "no_costs": {"cost_multiplier": 0.0},
    "costs_x2": {"cost_multiplier": 2.0},
    "costs_x3": {"cost_multiplier": 3.0},
    "delay_1": {"delay": 1},
    "delay_2": {"delay": 2},
    "participation_1pct": {"max_participation": 0.01},
    "capital_x10": {"capital_multiplier": 10.0},
}


def scenario_config(base: BacktestConfig, spec: dict[str, float]) -> BacktestConfig:
    cfg = base
    if "cost_multiplier" in spec:
        cfg = replace(cfg, costs=cfg.costs.scaled(spec["cost_multiplier"]))
    if "delay" in spec:
        cfg = replace(cfg, execution=replace(cfg.execution, delay=int(spec["delay"])))
    if "max_participation" in spec:
        cfg = replace(
            cfg, execution=replace(cfg.execution, max_participation=spec["max_participation"])
        )
    if "capital_multiplier" in spec:
        cfg = replace(cfg, initial_capital=cfg.initial_capital * spec["capital_multiplier"])
    if "rebalance_every" in spec:
        cfg = replace(
            cfg, strategy=replace(cfg.strategy, rebalance_every=int(spec["rebalance_every"]))
        )
    return cfg


def run_scenarios(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    base: BacktestConfig,
    scenarios: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    rows = []
    for name, spec in (scenarios or DEFAULT_SCENARIOS).items():
        m = compute_metrics(run_backtest(bars, signals, scenario_config(base, spec)))
        perf, trading = m["performance"], m["trading"]
        rows.append(
            {
                "scenario": name,
                **{f"param_{k}": v for k, v in spec.items()},
                "cagr": perf["cagr"]["value"],
                "sharpe": perf["sharpe"]["value"],
                "max_drawdown": perf["max_drawdown"]["value"],
                "total_costs": trading["total_costs"]["value"],
                "turnover_one_way_annual": trading["turnover_one_way_annual"]["value"],
                "participation_capped_fills": trading["participation_capped_fills"]["value"],
            }
        )
    return pd.DataFrame(rows)
