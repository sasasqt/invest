# ruff: noqa: E501  (evidence script kept as run)
"""trades.csv reports `shares` and `price` in total-return-adjusted units without saying so:
on the Yahoo replay, AAPL fills in 2010 show prices near 6-8 dollars and share counts about
28x the shares actually tradable (7:1 split 2014, 4:1 split 2020, dividends), and the same
row's values change whenever a later corporate action rescales the history."""

import json
import sys

import pandas as pd

from invest_data.yahoo import parse_chart

eval_dir, snap = sys.argv[1], sys.argv[2]
t = pd.read_csv(f"{eval_dir}/tables/trades.csv", parse_dates=["date"])
a = t[(t["instrument"] == "AAPL") & (t["status"] == "filled")].head(3)
raw = parse_chart(json.loads(open(f"{snap}/raw/AAPL.json", "rb").read()), "AAPL").set_index("date")
for _, r in a.iterrows():
    split_adj_open = raw.loc[r["date"], "open"]
    # Yahoo open is split-adjusted; as-traded open in 2010-2013 = split-adjusted x 28 (7:1 then 4:1)
    print(
        f"{r['date'].date()} trades.csv price={r['price']:.4f} shares={r['shares']:.1f} | "
        f"as-traded open ~= {split_adj_open * 28:.2f}, as-traded shares ~= {r['notional'] / (split_adj_open * 28):.1f}"
    )
print("README/REPORTING: no statement that trades.csv prices and shares are adjusted units")
