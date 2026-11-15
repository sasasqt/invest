"""open_place 3 (reviewer 2, 2026-11-08): parse_chart + total_return_adjust/clean_bars with
trailing rows whose close is present but adjclose is null (feed mid-update). Does the factor
for earlier rows become NaN and drop history silently?
Usage: uv run python ra_yahoo_trailing_adjclose_null.py"""
import json
import numpy as np
from invest_data.yahoo import parse_chart
from invest_data.cleaning import clean_bars, total_return_adjust

n = 8
stamps = [1704200400 + 86400 * i for i in range(n)]  # 2024-01-02.. 09:00 New York
close = [100 + i for i in range(n)]
adj = [c * 0.9 for c in close]
adj[-2:] = [None, None]  # trailing nulls
payload = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York", "currency": "USD",
    "exchangeName": "NYQ", "instrumentType": "EQUITY"}, "timestamp": stamps,
    "indicators": {"quote": [{"open": close, "high": close, "low": close, "close": close, "volume": [1000] * n}],
                   "adjclose": [{"adjclose": adj}]}}], "error": None}}
raw = parse_chart(json.dumps(payload).encode(), "AAA")
print("parsed rows", len(raw), "adjclose NaN rows", int(raw["adjclose"].isna().sum()))
adjusted = total_return_adjust(raw)
print("adjusted close:", np.round(adjusted["close"].to_numpy(), 4).tolist())
bars, report = clean_bars(raw, adjusted_close="adjclose")
print("clean_bars summary:", report.summary())
print("kept dates:", [str(d.date()) for d in bars["date"]])
ok = len(bars) == n - 2 and np.allclose(bars["close"].to_numpy(), [c * 0.9 for c in close[:-2]]) and report.summary().get("rejected_rows") == 2
print("verdict:", "PASS: per-row factor; the two trailing rows are rejected and counted in the cleaning report (invalid_adjusted_close), earlier rows keep their adjusted values; nothing is dropped silently" if ok else "UNEXPECTED: see above")
