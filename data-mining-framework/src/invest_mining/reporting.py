"""Factor report artifacts: tables, JSON summaries, and figures rendered from saved data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False) + "\n")


def write_factor_report(
    out: str | os.PathLike[str],
    *,
    expression: str,
    summary: dict[str, Any],
    ic: pd.DataFrame,
    quantiles: pd.DataFrame,
    tails: pd.DataFrame,
    config: dict[str, Any],
) -> Path:
    root = Path(out)
    (root / "tables").mkdir(parents=True, exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    ic.to_csv(root / "tables" / "daily_ic.csv")
    quantiles.to_csv(root / "tables" / "quantile_returns.csv")
    tails.to_csv(root / "tables" / "tail_returns.csv")
    _json(root / "config.json", config)
    _json(root / "metrics.json", {"expression": expression, **summary})
    render_factor_figures(root)
    return root


def render_factor_figures(root: Path) -> None:
    """Render figures only from saved tables (never recompute statistics here)."""
    ic = pd.read_csv(root / "tables" / "daily_ic.csv", index_col=0, parse_dates=True)
    q = pd.read_csv(root / "tables" / "quantile_returns.csv", index_col=0, parse_dates=True)

    fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax[0].bar(ic.index, ic["ic"], width=1.0, color="#9aa7b8")
    ax[0].plot(ic["ic"].rolling(60, min_periods=20).mean(), color="#1f4e79", label="60d mean")
    ax[0].axhline(0, color="black", lw=0.6)
    ax[0].set_ylabel("rank IC")
    ax[0].legend(loc="upper left")
    ax[1].plot(ic["ic"].fillna(0).cumsum(), color="#1f4e79")
    ax[1].set_ylabel("cumulative rank IC")
    ax[0].set_title("Daily rank IC (undefined dates shown as gaps)")
    fig.tight_layout()
    fig.savefig(root / "figures" / "ic.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    means = q.mean() * 1e4
    ax[0].bar(range(1, len(means) + 1), means.to_numpy(), color="#1f4e79")
    ax[0].set_xlabel("bucket (1 = lowest score)")
    ax[0].set_ylabel("mean forward return (bp)")
    ax[0].set_title("Quantile profile (signal diagnostic, not a portfolio)")
    spread = (q.iloc[:, -1] - q.iloc[:, 0]).fillna(0)
    ax[1].plot((1 + spread).cumprod(), color="#1f4e79")
    ax[1].set_title("Cumulative top-minus-bottom spread (idealised, no costs)")
    fig.tight_layout()
    fig.savefig(root / "figures" / "quantiles.png", dpi=120)
    plt.close(fig)
