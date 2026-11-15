"""Check: `download_snapshot` promises that "symbols that fail after retries are recorded under failures rather
than aborting the whole download" (invest_data/yahoo.py:180-183), and `fetch_symbol` says network errors are
retried (yahoo.py:120-124). `http_get` reads the body with `resp.read()`, which raises `http.client.IncompleteRead`
when the transfer is cut short. `fetch_symbol` catches `urllib.error.URLError`, `TimeoutError` and `ConnectionError`
(yahoo.py:138) but not `http.client.HTTPException`, so a truncated response is neither retried nor recorded: it
propagates, the staged files are discarded and the whole download stops with a traceback.

Usage: python ra_download_snapshot_aborts_on_truncated_response.py <tmp dir>
Exit 0 when the truncated symbol is retried or recorded as a failure, 1 when the download aborts (the finding),
2 on setup error.
"""
from __future__ import annotations

import http.client
import json
import shutil
import sys
from pathlib import Path

try:
    from invest_data import yahoo
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import fake_chart
except Exception as exc:  # pragma: no cover
    print("setup error:", exc)
    sys.exit(2)

tmp = Path(sys.argv[1])
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True)
bars = synthetic_market(SyntheticConfig(n_instruments=1, n_days=5, seed=3))
good = json.dumps(fake_chart(bars, "AAA")).encode()
calls: list[str] = []


def fetcher(url, timeout):
    symbol = url.split("/chart/", 1)[1].split("?", 1)[0]
    calls.append(symbol)
    if symbol == "CUT":
        raise http.client.IncompleteRead(good[:100], expected=len(good) - 100)  # transfer cut short
    return good


try:
    snap = yahoo.download_snapshot(
        ["AAA", "CUT", "BBB"], "2020-01-01", "2020-02-01", tmp / "s", fetcher=fetcher, sleep=lambda s: None
    )
except http.client.HTTPException as exc:
    print(f"FAIL: the whole download aborted on one truncated response: {type(exc).__name__}: {exc}")
    print(f"      requests made: {calls} (BBB was never fetched); published: {sorted(p.name for p in tmp.iterdir())}")
    sys.exit(1)
retried = calls.count("CUT") > 1
print(f"requests: {calls}; failures: {snap['failures']}")
if "CUT" in snap["failures"] and sorted(snap["files"]) == ["AAA", "BBB"]:
    print("PASS: the truncated symbol was", "retried and" if retried else "", "recorded as a failure")
    sys.exit(0)
print("FAIL: unexpected manifest")
sys.exit(1)
