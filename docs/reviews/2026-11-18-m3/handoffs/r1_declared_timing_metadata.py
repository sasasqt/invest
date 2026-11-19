# ruff: noqa: E402  (evidence script kept as run)
"""Universe and fundamentals bundles declare their timing convention in metadata
(``interval``, ``available_at``), but the publishers let a caller override it and the readers
never look at it, unlike signals (publish_signals/read_signals refuse any available_at other
than decision_date_close). A bundle that declares another convention is read with the
contract's one, silently."""

import shutil
import sys
from pathlib import Path

import pandas as pd

from invest_data.pit import fundamentals_asof, membership_panel
from invest_data.schemas import (
    publish_fundamentals,
    publish_signals,
    publish_universe,
    read_fundamentals,
    read_universe,
)

out = Path(sys.argv[1])
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
dates = pd.bdate_range("2024-01-01", periods=6)
uni = pd.DataFrame(
    {"universe": ["U"], "instrument": ["A"], "start_date": [dates[0]], "end_date": [dates[3]]}
)
publish_universe(
    uni, out / "uni", dataset_id="u", metadata={"interval": "start_date <= date <= end_date"}
)
m, rows = read_universe(out / "uni")
member = membership_panel(rows, dates, pd.Index(["A"]))["A"]
print("universe declared interval:", m.metadata["interval"])
print(
    f"  member on end_date {dates[3].date()}: observed {bool(member.iloc[3])}, expected per its "
    "declaration True (or a refusal of the declaration)"
)

fund = pd.DataFrame(
    {
        "instrument": ["A"],
        "field": ["eps"],
        "period_end": [dates[0]],
        "available_date": [dates[2]],
        "value": [1.0],
    }
)
publish_fundamentals(
    fund, out / "fund", dataset_id="f", metadata={"available_at": "available_date_next_open"}
)
m, rows = read_fundamentals(out / "fund")
seen = fundamentals_asof(rows, "eps", dates, pd.Index(["A"]))["A"]
print("fundamentals declared available_at:", m.metadata["available_at"])
print(
    f"  value used at the close of {dates[2].date()}: observed {seen.iloc[2]}, expected per its "
    "declaration NaN (known only at the next open) or a refusal"
)

sig = pd.DataFrame({"decision_date": [dates[0]], "instrument": ["A"], "score": [1.0]})
try:
    publish_signals(
        sig,
        out / "sig",
        dataset_id="s",
        metadata={"factor_id": "f", "horizon_days": 1, "available_at": "next_open"},
    )
    print("signals: accepted")
except Exception as exc:  # the asymmetry: signals enforce their declared timing
    print("signals with another available_at: refused ->", type(exc).__name__, str(exc)[:80])

# signal_type is required but never read: a declared lower-is-better rank is read as a score.
publish_signals(
    sig,
    out / "sig_rank",
    dataset_id="s2",
    metadata={"factor_id": "f", "horizon_days": 1, "signal_type": "rank_1_is_best"},
)
from invest_data.schemas import read_signals

m, _ = read_signals(out / "sig_rank")
print(
    "signals declared signal_type:",
    m.metadata["signal_type"],
    "-> accepted; evaluation treats higher as more attractive",
)
