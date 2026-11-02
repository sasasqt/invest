"""Factor report artifacts: tables, JSON summaries, and figures rendered from saved data."""

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


def _json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )


def write_factor_report(
    out: str | os.PathLike[str],
    *,
    expression: str,
    summary: dict[str, Any],
    ic: pd.DataFrame,
    quantiles: pd.DataFrame,
    quantile_summary: pd.DataFrame,
    tails: pd.DataFrame,
    config: dict[str, Any],
) -> Path:
    root = Path(out)
    (root / "tables").mkdir(parents=True, exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    ic.to_csv(root / "tables" / "daily_ic.csv")
    quantiles.to_csv(root / "tables" / "quantile_returns.csv")
    quantile_summary.to_csv(root / "tables" / "quantile_summary.csv")
    tails.to_csv(root / "tables" / "tail_returns.csv")
    _json(root / "config.json", config)
    _json(root / "metrics.json", {"expression": expression, **summary})
    render_factor_figures(root)
    return root


def staggered_spread_wealth(spread: pd.Series, horizon: int) -> pd.Series:
    """Growth of 1 split evenly over ``horizon`` staggered cohorts of the h-day spread.

    ``spread`` holds overlapping h-day forward returns, one per decision date. Cohort
    ``k`` trades on every ``horizon``-th date from position ``k``, so each cohort compounds
    non-overlapping periods; compounding every date would count each day ``horizon``
    times. A cohort holds cash when its date's spread is undefined. The result is NaN on
    dates whose spread is undefined, so a figure shows them as gaps, not as 0% returns.

    The series is indexed by decision date: the value at date ``t`` already includes the
    ``horizon``-day outcome of the spread decided at ``t``, a hold from the open of ``t + 1``
    to the open of ``t + 1 + horizon`` that is only known then. It is a forward-outcome
    diagnostic, not wealth realised by that date.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    position = np.arange(len(spread))
    wealth = pd.Series(0.0, index=spread.index)
    for k in range(horizon):
        cohort = spread.where(position % horizon == k).fillna(0.0)
        wealth += (1.0 + cohort).cumprod() / horizon
    return wealth.where(spread.notna())


def render_factor_figures(root: Path) -> None:
    """Render figures only from saved tables (never recompute statistics here)."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    ic = pd.read_csv(root / "tables" / "daily_ic.csv", index_col=0, parse_dates=True)
    q = pd.read_csv(root / "tables" / "quantile_returns.csv", index_col=0, parse_dates=True)
    summary = pd.read_csv(root / "tables" / "quantile_summary.csv", index_col=0)

    fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax[0].bar(ic.index, ic["ic"], width=1.0, color="#9aa7b8")
    ax[0].plot(ic["ic"].rolling(60, min_periods=20).mean(), color="#1f4e79", label="60d mean")
    ax[0].axhline(0, color="black", lw=0.6)
    ax[0].set_ylabel("rank IC")
    ax[0].legend(loc="upper left")
    # Undefined dates add nothing and are drawn as gaps, not as 0 steps.
    ax[1].plot(ic["ic"].cumsum(), color="#1f4e79")
    ax[1].set_ylabel("cumulative rank IC")
    ax[0].set_title("Daily rank IC (undefined dates shown as gaps)")
    fig.tight_layout()
    fig.savefig(root / "figures" / "ic.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ok = summary["status"] == "ok"
    # Only buckets with status ok get a bar; the others are labelled, never drawn as 0.
    means = summary.loc[ok, "mean_forward_return"] * 1e4
    ax[0].bar(summary.loc[ok, "bucket"], means.to_numpy(), color="#1f4e79")
    ax[0].set_xticks(summary["bucket"].to_numpy())
    for bucket in summary.loc[~ok, "bucket"]:
        ax[0].annotate("insufficient\ndata", (bucket, 0), ha="center", va="bottom", fontsize=7)
    ax[0].set_xlabel("bucket (1 = lowest score)")
    ax[0].set_ylabel(f"mean {config['horizon']}-day forward return (bp)")
    ax[0].set_title("Quantile profile (signal diagnostic, not a portfolio)")
    spread = q.iloc[:, -1] - q.iloc[:, 0]
    ax[1].plot(staggered_spread_wealth(spread, int(config["horizon"])), color="#1f4e79")
    ax[1].set_title(
        f"Top-minus-bottom spread, {config['horizon']} staggered cohorts\n"
        f"(idealised, no costs; each {config['horizon']}-day outcome drawn on its decision "
        "date;\nundefined dates as gaps)",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(root / "figures" / "quantiles.png", dpi=120)
    plt.close(fig)
