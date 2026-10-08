"""Deterministic cleaning of raw daily bars, with an explicit rejected-row report.

Cleaning never fills, interpolates or forward-fills prices: those are modelling choices
that belong to consumers. Each rejected row carries the first rule it violated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED = ["date", "instrument", "open", "high", "low", "close", "volume"]
OPTIONAL = ["close_as_traded"]  # kept when the source has it


@dataclass(frozen=True)
class CleaningReport:
    input_rows: int
    output_rows: int
    rejected: pd.DataFrame  # original columns + "reason"

    def summary(self) -> dict[str, object]:
        counts = self.rejected["reason"].value_counts().sort_index()
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "rejected_rows": len(self.rejected),
            "rejected_by_reason": {str(k): int(v) for k, v in counts.items()},
        }


def clean_bars(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Return (clean bars sorted by date/instrument, report). Input is not modified."""
    missing_cols = [c for c in REQUIRED if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"raw bars missing columns {missing_cols}")
    columns = REQUIRED + [c for c in OPTIONAL if c in raw.columns]
    df = raw[columns].copy()
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], format="ISO8601", errors="coerce")
    df["date"] = df["date"].dt.normalize()
    df["instrument"] = df["instrument"].astype("string").str.strip()
    numeric = columns[2:]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    reason = pd.Series(pd.NA, index=df.index, dtype="object")

    def flag(mask: pd.Series, why: str) -> None:
        reason.loc[mask & reason.isna()] = why

    num = df[numeric].to_numpy(dtype="float64")
    flag(df["date"].isna(), "invalid_date")
    flag(df["instrument"].isna() | (df["instrument"] == ""), "missing_instrument")
    flag(pd.Series(~np.isfinite(num).all(axis=1), index=df.index), "missing_or_nonfinite_value")
    prices = [c for c in numeric if c != "volume"]
    flag((df[prices] <= 0).any(axis=1), "non_positive_price")
    flag(df["volume"] < 0, "negative_volume")
    flag(df["high"] < df[["open", "close"]].max(axis=1), "high_below_open_close")
    flag(df["low"] > df[["open", "close"]].min(axis=1), "low_above_open_close")
    order = df.assign(_row=np.arange(len(df))).sort_values(["date", "instrument", "_row"])
    dup = order.duplicated(["date", "instrument"], keep=False)
    flag(dup.reindex(df.index).fillna(False).astype(bool), "duplicate_key")

    bad = reason.notna()
    rejected = raw.loc[bad].copy()
    rejected["reason"] = reason[bad]
    clean = df.loc[~bad].sort_values(["date", "instrument"]).reset_index(drop=True)
    clean["instrument"] = clean["instrument"].astype(object)
    report = CleaningReport(len(raw), len(clean), rejected.reset_index(drop=True))
    return clean, report
