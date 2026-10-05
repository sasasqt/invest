"""Point-in-time helpers: universe membership and as-of fundamentals.

Both return wide (date x instrument) frames aligned to a trading calendar, using only
information available at the close of each date.
"""

from __future__ import annotations

import pandas as pd


def membership_panel(
    universe: pd.DataFrame,
    dates: pd.DatetimeIndex,
    instruments: pd.Index,
    name: str | None = None,
) -> pd.DataFrame:
    """Boolean frame: True where the instrument is a member on that date.

    ``name`` selects one universe when the table holds several (required then).
    """
    names = universe["universe"].unique()
    if name is None:
        if len(names) > 1:
            raise ValueError(f"several universes {sorted(names)}; pass name=")
    else:
        universe = universe[universe["universe"] == name]
    out = pd.DataFrame(False, index=dates, columns=instruments)
    for row in universe.itertuples(index=False):
        if row.instrument not in out.columns:
            continue
        mask = dates >= row.start_date
        if pd.notna(row.end_date):
            mask &= dates < row.end_date
        out.loc[mask, row.instrument] = True
    return out


def fundamentals_asof(
    fundamentals: pd.DataFrame,
    field: str,
    dates: pd.DatetimeIndex,
    instruments: pd.Index,
) -> pd.DataFrame:
    """Latest known value of ``field`` at each date's close.

    At date ``d`` only rows with ``available_date <= d`` are visible. Among them the most
    recent ``period_end`` wins, and for that period the latest revision wins. A late
    revision of an older period therefore never replaces a newer period's value.
    """
    rows = fundamentals[fundamentals["field"] == field]
    out = pd.DataFrame(float("nan"), index=dates, columns=instruments)
    for instrument, grp in rows.groupby("instrument"):
        if instrument not in out.columns:
            continue
        grp = grp.sort_values(["available_date", "period_end"])
        best: tuple[pd.Timestamp, pd.Timestamp] | None = None
        best_value = float("nan")
        events: dict[pd.Timestamp, float] = {}
        for r in grp.itertuples(index=False):
            key = (r.period_end, r.available_date)
            if best is None or key > best:
                best, best_value = key, float(r.value)
            events[r.available_date] = best_value
        series = pd.Series(events).sort_index()
        out[instrument] = series.reindex(dates, method="ffill")
    return out
