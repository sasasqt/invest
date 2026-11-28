#!/usr/bin/env bash
# import-csv declares frequency "1d" and calendar as given without looking at the dates:
# weekly bars (every 5th synthetic session) and bars dated on Saturdays publish as "1d"/"XNYS".
set -euo pipefail
R=${OUT:?set OUT to a scratch folder}
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
W=$R/work/import_freq; rm -rf "$W"; mkdir -p "$W"
$B/python - "$R/work/syn7" "$W" <<'PY'
import sys
from invest_data.schemas import read_market_bars
_, bars = read_market_bars(sys.argv[1])
dates = sorted(bars["date"].unique())
weekly = bars[bars["date"].isin(dates[::5])].drop(columns=["close_as_traded"])
weekly.assign(date=weekly["date"].dt.strftime("%Y-%m-%d")).to_csv(f"{sys.argv[2]}/weekly.csv", index=False)
sat = weekly.copy(); sat["date"] = sat["date"] + __import__("pandas").Timedelta(days=(5 - sat["date"].dt.weekday.iloc[0]) % 7)
sat.assign(date=sat["date"].dt.strftime("%Y-%m-%d")).to_csv(f"{sys.argv[2]}/saturday.csv", index=False)
gaps = __import__("pandas").Series(sorted(weekly["date"].unique())).diff().dt.days.median()
print("weekly.csv median gap between sessions (calendar days):", gaps)
PY
$B/invest-data import-csv "$W/weekly.csv" --out "$W/weekly" --dataset-id weekly --currency USD --calendar XNYS --price-adjustment total_return_adjusted > /dev/null
$B/invest-data import-csv "$W/saturday.csv" --out "$W/saturday" --dataset-id sat --currency USD --calendar XNYS --price-adjustment total_return_adjusted > /dev/null
$B/python - "$W" <<'PY'
import json, sys
import pandas as pd
from invest_data.schemas import read_market_bars
for name in ("weekly", "saturday"):
    m, bars = read_market_bars(f"{sys.argv[1]}/{name}")
    d = pd.Series(sorted(bars["date"].unique()))
    print(f"{name}: observed median gap {d.diff().dt.days.median()} days, weekdays {sorted(set(d.dt.day_name()))}; "
          f"published metadata frequency={m.metadata['frequency']!r} calendar={m.metadata['calendar']!r}")
print("expected: a refusal, or frequency matching the data (not '1d' for weekly bars; no Saturday sessions in XNYS)")
PY
# Downstream (known consumer side BH-2026-11-17-2 / BH-2026-11-18-1): the "1d" weekly bundle runs end to end.
cd "$W"
python3 -c "
import json;c=json.load(open('${INVEST:?set INVEST to an invest checkout at eb64ad8}/strategy-evaluation/examples/quantile_long_short.json'));c['execution']['min_price']=0.0;json.dump(c,open('cfg0.json','w'))"
$B/invest-mine freeze --expr "close / delay(close, 1) - 1" --horizon 1 --orientation -1 --out f.json > /dev/null
$B/invest-mine export --data weekly --factor f.json --out sig > /dev/null
$B/invest-eval run --data weekly --signals sig --config cfg0.json --out ev --no-scenarios
python3 -c "
import json;print('annualization used:', json.load(open('ev/config.json'))['annualization'], '| signals horizon_days:', json.load(open('sig/manifest.json'))['metadata']['horizon_days'], '(one bar = 7 calendar days)')"
