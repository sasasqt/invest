"""Persist backtest results, then render figures and a summary from the saved files only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from invest_evaluation.engine import BacktestResult


def _json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def save_run(
    out: str | os.PathLike[str],
    result: BacktestResult,
    metrics: dict[str, Any],
    statistics: dict[str, Any],
    scenarios: pd.DataFrame | None,
    provenance: dict[str, Any],
) -> Path:
    root = Path(out)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"run directory {root} is not empty")
    (root / "tables").mkdir(parents=True, exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    daily = result.daily.copy()
    daily["return"] = result.returns
    daily["gross_return"] = result.gross_returns
    daily["benchmark_return"] = result.benchmark
    daily.to_csv(root / "tables" / "daily.csv")
    result.trades.to_csv(root / "tables" / "trades.csv", index=False)
    result.episodes.to_csv(root / "tables" / "episodes.csv", index=False)
    if scenarios is not None:
        scenarios.to_csv(root / "tables" / "scenarios.csv", index=False)
    _json(root / "config.json", result.config.to_dict())
    _json(root / "metrics.json", metrics)
    _json(root / "statistics.json", _finite(statistics))
    _json(root / "manifest.json", {**provenance, "warnings": result.warnings})
    render(root)
    return root


def _finite(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def render(root: Path) -> None:
    d = pd.read_csv(root / "tables" / "daily.csv", index_col=0, parse_dates=True)
    cfg = json.loads((root / "config.json").read_text())
    v0 = cfg["initial_capital"]
    a = cfg["annualization"]

    fig, ax = plt.subplots(
        2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )
    ax[0].plot(d["equity"] / v0, label="net", color="#1f4e79")
    ax[0].plot(d["equity_before_costs"] / v0, label="before costs", color="#7fa7d1", lw=1)
    ax[0].plot(
        (1 + d["benchmark_return"]).cumprod(), label="universe EW (gross)", color="#999999", lw=1
    )
    ax[0].set_ylabel("growth of 1")
    ax[0].legend(loc="upper left")
    ax[0].set_title("Equity")
    wealth = np.concatenate([[v0], d["equity"].to_numpy()])
    dd = wealth / np.maximum.accumulate(wealth) - 1
    ax[1].fill_between(d.index, dd[1:] * 100, 0, color="#b33a3a", alpha=0.6)
    ax[1].set_ylabel("drawdown (%)")
    fig.tight_layout()
    fig.savefig(root / "figures" / "equity_drawdown.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    r = d["return"]
    roll = r.rolling(126, min_periods=63)
    ax[0, 0].plot(roll.mean() / roll.std() * np.sqrt(a), color="#1f4e79")
    ax[0, 0].axhline(0, color="black", lw=0.6)
    ax[0, 0].set_title("Rolling 6-month Sharpe (net)")
    ax[0, 1].hist(r * 1e4, bins=60, color="#1f4e79")
    ax[0, 1].set_title("Daily net returns (bp)")
    costs = d[["commission_cost", "spread_cost", "impact_cost", "borrow_cost"]].cumsum()
    ax[1, 0].stackplot(
        d.index, costs.T.to_numpy() / v0 * 100, labels=["commission", "spread", "impact", "borrow"]
    )
    ax[1, 0].legend(loc="upper left", fontsize=8)
    ax[1, 0].set_title("Cumulative costs (% of initial capital)")
    ax[1, 1].plot(d["gross_exposure"], label="gross", color="#1f4e79")
    ax[1, 1].plot(d["net_exposure"], label="net", color="#c07d10")
    ax[1, 1].legend(loc="upper left", fontsize=8)
    ax[1, 1].set_title("Exposure (fraction of NAV)")
    fig.tight_layout()
    fig.savefig(root / "figures" / "diagnostics.png", dpi=120)
    plt.close(fig)

    scen_path = root / "tables" / "scenarios.csv"
    if scen_path.exists():
        s = pd.read_csv(scen_path)
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.barh(s["scenario"], s["sharpe"].fillna(0), color="#1f4e79")
        ax.axvline(0, color="black", lw=0.6)
        ax.set_xlabel("net Sharpe")
        ax.set_title("Stress scenarios (fixed signal and rules)")
        fig.tight_layout()
        fig.savefig(root / "figures" / "scenarios.png", dpi=120)
        plt.close(fig)

    _write_summary(root)


def _fmt(m: dict[str, Any]) -> str:
    if m.get("value") is None:
        return f"n/a ({m.get('reason')})"
    v = m["value"]
    if isinstance(v, float):
        return f"{v:.2%}" if m.get("unit", "").startswith("fraction") else f"{v:,.3f}"
    return str(v)


def _write_summary(root: Path) -> None:
    metrics = json.loads((root / "metrics.json").read_text())
    stats = json.loads((root / "statistics.json").read_text())
    lines = ["# Backtest summary", ""]
    picks = {
        "performance": [
            "total_return",
            "cagr",
            "annual_volatility",
            "sharpe",
            "sortino",
            "calmar",
            "max_drawdown",
            "max_drawdown_duration",
            "var_loss_95",
            "expected_shortfall_95",
        ],
        "gross_of_costs": ["cagr", "sharpe"],
        "trading": [
            "total_costs",
            "cost_drag_annual",
            "turnover_one_way_annual",
            "average_gross_exposure",
            "rejected_orders",
            "participation_capped_fills",
        ],
        "trades": [
            "closed_trades",
            "win_rate",
            "payoff_ratio",
            "profit_factor",
            "average_holding_sessions",
        ],
        "benchmark": ["benchmark_total_return", "beta", "information_ratio"],
    }
    for section, keys in picks.items():
        lines += [f"## {section.replace('_', ' ').title()}", "", "| metric | value |", "|---|---|"]
        for k in keys:
            if k in metrics.get(section, {}):
                lines.append(f"| {k} | {_fmt(metrics[section][k])} |")
        lines.append("")
    b = stats.get("bootstrap", {})
    if b.get("status") == "ok":
        lo, hi = b["sharpe_ci"]
        lines.append(f"Sharpe {b['level']:.0%} stationary-bootstrap CI: [{lo:.2f}, {hi:.2f}]")
    dsr = stats.get("deflated_sharpe", {})
    if dsr.get("status") == "ok":
        lines.append(f"Deflated Sharpe ratio (n_trials={dsr['n_trials']}): {dsr['dsr']:.3f}")
    lines += ["", "Figures: `figures/`. Tables: `tables/`. Full metrics: `metrics.json`."]
    (root / "report.md").write_text("\n".join(lines) + "\n")
