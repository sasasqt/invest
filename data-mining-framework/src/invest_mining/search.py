"""Baseline alpha search: random expressions + seed templates, with a full trial ledger.

Protocol (ALPHA_VALIDATION.md §1-4):

1. Split decision dates chronologically into development and confirmation periods.
   Development decisions whose label interval reaches into the confirmation period are
   purged, plus an optional embargo.
2. Every proposal is recorded in the ledger, including duplicates and invalid formulas.
3. Orientation and selection use development data only. The top-k distinct candidates
   (by HAC t-statistic of oriented rank IC, after a redundancy filter) form the frozen
   confirmatory family.
4. The family is tested once on confirmation data, one-sided in the pre-specified
   direction, with Holm adjustment over the family.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from invest_mining.artifact import FrozenFactor
from invest_mining.diagnostics import (
    daily_ic,
    forward_returns,
    holm_adjust,
    ic_summary,
    newey_west_lags,
    newey_west_mean_test,
)
from invest_mining.expressions import (
    ExpressionError,
    Node,
    canonical,
    evaluate,
    lookback,
    parse,
    random_expression,
    restrict,
    size,
)

SEED_TEMPLATES = (
    "close / delay(close, 5) - 1",
    "close / delay(close, 20) - 1",
    "ts_mean(returns, 10)",
    "ts_std(returns, 20)",
    "volume / ts_mean(volume, 20)",
    "intraday_return",
    "ts_corr(returns, volume, 10)",
)


@dataclass(frozen=True)
class Split:
    dev_dates: pd.DatetimeIndex
    confirm_dates: pd.DatetimeIndex
    purged_dates: pd.DatetimeIndex

    def to_dict(self) -> dict[str, Any]:
        def rng(ix: pd.DatetimeIndex) -> list[str] | None:
            return [str(ix[0].date()), str(ix[-1].date())] if len(ix) else None

        return {
            "development": rng(self.dev_dates),
            "confirmation": rng(self.confirm_dates),
            "purged": rng(self.purged_dates),
            "n_development": len(self.dev_dates),
            "n_confirmation": len(self.confirm_dates),
        }


def chronological_split(
    dates: pd.DatetimeIndex, dev_fraction: float, horizon: int, embargo: int = 0
) -> Split:
    """Dev decision ``i`` uses sessions up to ``i+1+h``; keep only ``i+1+h < k+1``."""
    if not 0 < dev_fraction < 1:
        raise ValueError("dev_fraction must be in (0, 1)")
    k = int(len(dates) * dev_fraction)
    cut = max(k - horizon - embargo, 0)
    return Split(dates[:cut], dates[k:], dates[cut:k])


@dataclass
class SearchResult:
    ledger: pd.DataFrame
    family: list[FrozenFactor]
    confirmation: pd.DataFrame
    split: Split
    config: dict[str, Any] = field(default_factory=dict)


def _oriented_stats(values: pd.DataFrame, label: pd.DataFrame, horizon: int) -> dict[str, Any]:
    ic = daily_ic(values, label, "spearman")
    s = ic_summary(ic, horizon)
    return {"summary": s, "ic": ic["ic"]}


def run_search(
    panel: dict[str, pd.DataFrame],
    *,
    n_trials: int = 200,
    seed: int = 0,
    horizon: int = 1,
    dev_fraction: float = 0.6,
    embargo: int = 0,
    top_k: int = 5,
    max_depth: int = 4,
    max_size: int = 15,
    max_lookback: int = 120,
    min_coverage: float = 0.5,
    max_family_corr: float = 0.7,
    alpha: float = 0.05,
    dataset_id: str = "",
    dataset_sha256: str | None = None,
) -> SearchResult:
    rng = np.random.default_rng(seed)
    label = restrict(forward_returns(panel["open"], horizon), panel)
    split = chronological_split(
        pd.DatetimeIndex(panel["close"].index), dev_fraction, horizon, embargo
    )
    dev_label = label.loc[split.dev_dates]

    proposals: list[tuple[str, Node | None, str | None]] = []
    for text in SEED_TEMPLATES:
        proposals.append(("template", parse(text), None))
    for _ in range(n_trials):
        try:
            proposals.append(("random", random_expression(rng, max_depth), None))
        except ExpressionError as exc:  # pragma: no cover - generator emits valid trees
            proposals.append(("random", None, str(exc)))

    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    dev_values: dict[str, pd.DataFrame] = {}
    for trial, (origin, node, error) in enumerate(proposals):
        row: dict[str, Any] = {"trial": trial, "origin": origin, "expression": None}
        rows.append(row)
        if node is None:
            row.update(status="invalid", reason=error)
            continue
        text = canonical(node)
        row["expression"] = text
        row["size"] = size(node)
        row["lookback"] = lookback(node)
        if text in seen:
            row.update(status="duplicate", reason=f"same as trial {seen[text]}")
            continue
        seen[text] = trial
        if row["size"] > max_size or row["lookback"] > max_lookback:
            row.update(status="rejected", reason="complexity_limit")
            continue
        values = restrict(evaluate(node, panel), panel).loc[split.dev_dates]
        coverage = float(values.notna().sum().sum() / max(dev_label.notna().sum().sum(), 1))
        row["dev_coverage"] = coverage
        if coverage < min_coverage:
            row.update(status="rejected", reason="low_coverage")
            continue
        stats = _oriented_stats(values, dev_label, horizon)["summary"]
        test = stats["hac_test"]
        if test["status"] != "ok":
            row.update(status="rejected", reason=f"dev_test_{test['status']}")
            continue
        orientation = 1 if test["mean"] >= 0 else -1
        row.update(
            status="evaluated",
            orientation=orientation,
            dev_mean_rank_ic=orientation * test["mean"],
            dev_t=orientation * test["t_stat"],
            dev_valid_dates=stats["valid_dates"],
        )
        dev_values[text] = values * orientation

    ledger = pd.DataFrame(rows)
    family = _select_family(ledger, dev_values, top_k, max_family_corr)
    for text in family:
        ledger.loc[ledger["expression"] == text, "selected"] = True
    ledger["selected"] = ledger.get("selected", pd.Series(False, index=ledger.index))
    ledger["selected"] = ledger["selected"].fillna(False).astype(bool)

    frozen = []
    for text in family:
        r = ledger[(ledger["expression"] == text) & (ledger["status"] == "evaluated")].iloc[0]
        frozen.append(
            FrozenFactor(
                expression=text,
                orientation=int(r["orientation"]),
                horizon_days=horizon,
                training_start=str(split.dev_dates[0].date()),
                training_end=str(split.dev_dates[-1].date()),
                dataset_id=dataset_id,
                dataset_sha256=dataset_sha256,
                selection={
                    "method": "random_search+templates",
                    "seed": seed,
                    "n_proposals": len(proposals),
                    "n_unique": len(seen),
                    "dev_mean_rank_ic": float(r["dev_mean_rank_ic"]),
                    "dev_t": float(r["dev_t"]),
                },
            )
        )
    confirmation = confirm(frozen, panel, label.loc[split.confirm_dates], horizon, alpha)
    config = {
        "n_trials": n_trials,
        "seed": seed,
        "horizon": horizon,
        "dev_fraction": dev_fraction,
        "embargo": embargo,
        "top_k": top_k,
        "max_depth": max_depth,
        "max_size": max_size,
        "max_lookback": max_lookback,
        "min_coverage": min_coverage,
        "max_family_corr": max_family_corr,
        "alpha": alpha,
        "split": split.to_dict(),
    }
    return SearchResult(ledger, frozen, confirmation, split, config)


def _select_family(
    ledger: pd.DataFrame, values: dict[str, pd.DataFrame], top_k: int, max_corr: float
) -> list[str]:
    """Greedy by dev t-stat, skipping candidates too correlated with already chosen ones."""
    if "dev_t" not in ledger:
        return []
    ranked = ledger[ledger["status"] == "evaluated"].sort_values("dev_t", ascending=False)
    chosen: list[str] = []
    for text in ranked["expression"]:
        cand = values[text]
        redundant = False
        for other in chosen:
            ic = daily_ic(cand, values[other], "spearman")["ic"]
            if ic.notna().any() and abs(float(ic.mean())) > max_corr:
                redundant = True
                break
        if not redundant:
            chosen.append(text)
        if len(chosen) == top_k:
            break
    return chosen


def confirm(
    family: list[FrozenFactor],
    panel: dict[str, pd.DataFrame],
    confirm_label: pd.DataFrame,
    horizon: int,
    alpha: float = 0.05,
    min_dates: int = 60,
) -> pd.DataFrame:
    """Test the frozen family once on confirmation data (one-sided, Holm-adjusted)."""
    rows = []
    for factor in family:
        values = (
            restrict(evaluate(factor.expression, panel), panel).loc[confirm_label.index]
            * factor.orientation
        )
        ic = daily_ic(values, confirm_label, "spearman")["ic"].dropna()
        test = newey_west_mean_test(ic, newey_west_lags(len(ic), horizon), min_n=min_dates)
        rows.append(
            {
                "factor_id": factor.factor_id,
                "expression": factor.expression,
                "orientation": factor.orientation,
                "confirm_mean_rank_ic": test.mean,
                "confirm_t": test.t_stat,
                "p_one_sided": test.p_one_sided,
                "n_dates": test.n,
                "hac_lags": test.lags,
                "test_status": test.status,
            }
        )
    out = pd.DataFrame(
        rows,
        columns=[
            "factor_id",
            "expression",
            "orientation",
            "confirm_mean_rank_ic",
            "confirm_t",
            "p_one_sided",
            "n_dates",
            "hac_lags",
            "test_status",
        ],
    )
    if out.empty:
        out["p_holm"] = pd.Series(dtype=float)
        out["family_size"] = pd.Series(dtype=int)
        out["status"] = pd.Series(dtype=str)
        return out
    ok = out["test_status"] == "ok"
    pvals = [
        p if (s and math.isfinite(p)) else 1.0 for p, s in zip(out["p_one_sided"], ok, strict=True)
    ]
    out["p_holm"] = holm_adjust(pvals)
    out["family_size"] = len(out)
    out["status"] = np.where(
        ~ok, "inconclusive", np.where(out["p_holm"] <= alpha, "confirmation_passed", "rejected")
    )
    return out
