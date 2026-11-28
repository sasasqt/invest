"""R3 probe: weekly bars imported with the documented import-csv command are declared
frequency '1d' (cli.py:262) with no check of the bar spacing."""

import pandas as pd

from invest_data.sources import SyntheticConfig, synthetic_market

bars = synthetic_market(SyntheticConfig(n_instruments=40, n_days=1500, seed=3))
dates = sorted(bars["date"].unique())
weekly = set(dates[::5])  # one bar per week (every fifth weekday)
w = bars[bars["date"].isin(weekly)].drop(columns="close_as_traded")
w.to_csv("out/weekly.csv", index=False)
gaps = pd.Series(sorted(weekly)).diff().dt.days.value_counts()
print("rows", len(w), "sessions", len(weekly), "spacing days:", gaps.to_dict())
