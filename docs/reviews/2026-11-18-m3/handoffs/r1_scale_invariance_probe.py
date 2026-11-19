"""Numerical probe of the mining scale check: for formulas check_scale_free accepts (hand list
plus 400 search draws), rescale one instrument's history before date T as a later corporate
action would (prices x c, volume / c, close_as_traded unchanged) and compare values before T.
A formula that passes the check but changes = a gap (ignoring the known REVIEW-47/48 residue
on flat windows, which synthetic prices do not have)."""

import sys

import numpy as np
import pandas as pd

from invest_data.schemas import read_market_bars
from invest_mining.expressions import (
    ScaleError,
    build_panel,
    check_scale_free,
    evaluate,
    parse,
    random_expression,
    restrict,
)

_, bars = read_market_bars(sys.argv[1])
bars = bars[bars["date"] < "2021-06-01"]
dates = sorted(bars["date"].unique())
T = dates[200]
sym = "SYN003"
c = 0.37
alt = bars.copy()
m = (alt["instrument"] == sym) & (alt["date"] < T)
for f in ("open", "high", "low", "close"):
    alt.loc[m, f] *= c
alt.loc[m, "volume"] /= c
p0, p1 = build_panel(bars), build_panel(alt)
hand = [
    "close / delay(close, 5) - 1",
    "(high - low) / close",
    "close / ts_max(close, 60)",
    "delta(log(close), 5)",
    "ts_rank(close, 20)",
    "ts_corr(close, volume, 20)",
    "sign(delta(close, 5))",
    "volume / ts_mean(volume, 20)",
    "log(dollar_volume)",
    "cs_rank(close_as_traded)",
    "open * close_as_traded / close",
    "volume * close / close_as_traded",
    "cs_zscore(ts_std(returns, 20))",
    "ts_min(low, 10) / ts_max(high, 10)",
    "log(high) - log(low)",
    "ts_sum(log(close), 5) - 5 * log(close)",
    "abs(delta(close, 3)) / close",
    "cs_rank(ts_mean(intraday_return, 5) * dollar_volume)",
    "ts_std(log(volume), 10)",
    "delta(log(volume), 5) + delta(log(close), 5)",
    "ts_mean(close, 5) / ts_mean(open, 5)",
]
rng = np.random.default_rng(11)
draws = [str(random_expression(rng)) for _ in range(400)]
gaps, checked, refused = [], 0, []
for text in hand + draws:
    try:
        check_scale_free(parse(text))
    except ScaleError:
        refused.append(text)
        continue
    a = restrict(evaluate(text, p0), p0).loc[: T - pd.Timedelta(days=1), sym]
    b = restrict(evaluate(text, p1), p1).loc[: T - pd.Timedelta(days=1), sym]
    ok = np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True) | (a.isna() & b.isna())
    checked += 1
    if not ok.all():
        gaps.append((text, int((~ok).sum()), float(np.nanmax(np.abs(a - b)))))
# cross-sectional operators: compare the instrument's value against others on dates < T
print(f"accepted formulas probed: {checked}; refused by the check: {len(refused)}")
print("hand-list refusals:", [h for h in hand if h in refused])
print("accepted but changed by a later rescale (expected none):", gaps[:10])
