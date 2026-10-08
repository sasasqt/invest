"""Deterministic cleaning of raw daily bars, with an explicit rejected-row report.

Cleaning never fills, interpolates or forward-fills prices: those are modelling choices
that belong to consumers. Each rejected row carries the first rule it violated. An invalid
value in an optional column is nulled and counted instead, so the bar itself is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from invest_data.schemas import AS_TRADED_CLOSE, non_real

REQUIRED = ["date", "instrument", "open", "high", "low", "close", "volume"]
OPTIONAL = [AS_TRADED_CLOSE.name]  # positive prices, kept when the source has them
# Values that mean "unknown" in an optional column, compared case-insensitively
# (pandas' default CSV null markers).
NULL_TOKENS = frozenset(
    {"", "#n/a", "#n/a n/a", "#na", "-1.#ind", "-1.#qnan", "-nan", "1.#ind", "1.#qnan", "<na>",
     "n/a", "na", "nan", "none", "null"}
)  # fmt: skip


@dataclass(frozen=True)
class CleaningReport:
    input_rows: int
    output_rows: int
    rejected: pd.DataFrame  # original columns + "reason"
    # Optional columns present: output rows whose value was invalid and set to null.
    nulled: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        counts = self.rejected["reason"].value_counts().sort_index()
        out: dict[str, object] = {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "rejected_rows": len(self.rejected),
            "rejected_by_reason": {str(k): int(v) for k, v in counts.items()},
        }
        if self.nulled:
            out["nulled_invalid_values"] = dict(self.nulled)
        return out


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
    for col in columns[2:]:
        # Booleans and complex numbers would parse as numbers; they are not quantities.
        values = df[col].astype(object).mask(non_real(df[col]))
        df[col] = pd.to_numeric(values, errors="coerce").astype("float64")

    reason = pd.Series(pd.NA, index=df.index, dtype="object")

    def flag(mask: pd.Series, why: str) -> None:
        reason.loc[mask & reason.isna()] = why

    invalid = {}
    for col in columns[len(REQUIRED) :]:
        # A null marker means unknown. Any other value that is not a positive number is
        # invalid; it is nulled and counted, because the optional column must not cost the
        # session its bar.
        suspect = ~(np.isfinite(df[col]) & (df[col] > 0))
        text = raw.loc[suspect, col]
        given = text.notna() & ~text.astype(str).str.strip().str.lower().isin(NULL_TOKENS)
        invalid[col] = given.reindex(df.index, fill_value=False)
        df.loc[invalid[col], col] = np.nan

    num = df[REQUIRED[2:]].to_numpy(dtype="float64")
    flag(df["date"].isna(), "invalid_date")
    flag(df["instrument"].isna() | (df["instrument"] == ""), "missing_instrument")
    flag(pd.Series(~np.isfinite(num).all(axis=1), index=df.index), "missing_or_nonfinite_value")
    flag((df[["open", "high", "low", "close"]] <= 0).any(axis=1), "non_positive_price")
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
    nulled = {col: int((mask & ~bad).sum()) for col, mask in invalid.items()}
    report = CleaningReport(len(raw), len(clean), rejected.reset_index(drop=True), nulled)
    return clean, report
