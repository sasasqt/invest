"""Check Yahoo snapshot semantics around known splits: are close and volume split-adjusted?
And does the published bundle keep close*volume == raw close*raw volume?"""

import json
import sys

import pandas as pd

from invest_data.cleaning import total_return_adjust
from invest_data.yahoo import parse_chart

snap = sys.argv[1]
cases = {
    "AAPL": "2020-08-31",
    "NVDA": "2021-07-20",
    "TSLA": "2020-08-31",
    "GOOGL": "2022-07-18",
    "AMZN": "2022-06-06",
}
for sym, d in cases.items():
    payload = json.loads(open(f"{snap}/raw/{sym}.json", "rb").read())
    raw = parse_chart(payload, sym).set_index("date")
    d = pd.Timestamp(d)
    w = raw.loc[
        d - pd.Timedelta(days=6) : d + pd.Timedelta(days=4), ["close", "adjclose", "volume"]
    ]
    print(sym, d.date())
    print(w.to_string())
    split = payload["chart"]["result"][0].get("events", {}).get("splits")
    print(" split events in snapshot:", None if split is None else len(split))
    adj = total_return_adjust(raw.reset_index())
    dv_raw = (raw["close"] * raw["volume"]).to_numpy()
    dv_adj = (adj["close"] * adj["volume"]).to_numpy()
    print(
        " max rel diff close*volume adjusted vs split-adj:", float(abs(dv_adj / dv_raw - 1).max())
    )
