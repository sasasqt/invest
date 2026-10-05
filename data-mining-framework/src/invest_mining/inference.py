"""Apply frozen factors to market data and export timestamped signals. No fitting here."""

from __future__ import annotations

import os

import pandas as pd

from invest_data.bundle import Manifest
from invest_data.schemas import publish_signals
from invest_mining.artifact import FrozenFactor
from invest_mining.expressions import build_panel, evaluate


def compute_scores(factor: FrozenFactor, bars: pd.DataFrame) -> pd.DataFrame:
    """Long frame ``decision_date, instrument, score`` (oriented: higher = more attractive).

    Only instruments with a bar on the decision date receive a score, so a value can never
    be produced for an instrument that was not trading at decision time.
    """
    panel = build_panel(bars)
    values = evaluate(factor.expression, panel) * factor.orientation
    values = values.where(panel["close"].notna())
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
) -> Manifest:
    """Publish a signals bundle. ``start`` limits output dates (history is still used)."""
    scores = compute_scores(factor, bars)
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
