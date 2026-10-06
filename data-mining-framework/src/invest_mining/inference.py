"""Apply frozen factors to market data and export timestamped signals. No fitting here."""

from __future__ import annotations

import os

import pandas as pd

from invest_data.bundle import Manifest
from invest_data.schemas import publish_signals
from invest_mining.artifact import FrozenFactor
from invest_mining.expressions import build_panel, evaluate, restrict


def compute_scores(
    factor: FrozenFactor,
    bars: pd.DataFrame,
    *,
    universe: pd.DataFrame | None = None,
    fundamentals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Long frame ``decision_date, instrument, score`` (oriented: higher = more attractive).

    Only instruments with a bar on the decision date (and, with a universe, members on that
    date) receive a score, so no value is produced for an instrument that was not
    tradable or eligible at decision time.
    """
    panel = build_panel(bars, universe=universe, fundamentals=fundamentals)
    values = evaluate(factor.expression, panel) * factor.orientation
    values = restrict(values, panel)
    long = values.stack().rename("score").reset_index()
    long.columns = ["decision_date", "instrument", "score"]
    return long.dropna().sort_values(["decision_date", "instrument"]).reset_index(drop=True)


def export_signals(
    factor: FrozenFactor,
    bars: pd.DataFrame,
    out: str | os.PathLike[str],
    *,
    dataset_id: str,
    start: str | None = None,
    fmt: str = "csv",
    universe: pd.DataFrame | None = None,
    fundamentals: pd.DataFrame | None = None,
) -> Manifest:
    """Publish a signals bundle. ``start`` limits output dates (history is still used)."""
    scores = compute_scores(factor, bars, universe=universe, fundamentals=fundamentals)
    if start is not None:
        scores = scores[scores["decision_date"] >= pd.Timestamp(start)]
    return publish_signals(
        scores,
        out,
        dataset_id=f"signals-{factor.factor_id}",
        metadata={
            "factor_id": factor.factor_id,
            "expression": factor.expression,
            "horizon_days": factor.horizon_days,
            "training_end": factor.training_end,
            "operator_version": factor.operator_version,
        },
        provenance={"market_dataset_id": dataset_id, "factor": factor.to_json()},
        fmt=fmt,
    )
