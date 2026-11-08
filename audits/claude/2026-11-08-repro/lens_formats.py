"""Contracts lens: the csv, sqlite and parquet bundles of the formats case must load to the same logical content, and the mining step
that read them must give the same results. Usage: python lens_formats.py <bench dir with formats-csv|sqlite|parquet>
Exit 0 when identical, 1 otherwise."""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from invest_data.schemas import read_fundamentals, read_market_bars, read_universe

bench = Path(sys.argv[1])
bad = 0
loaded = {}
for fmt in ("csv", "sqlite", "parquet"):
    root = bench / f"formats-{fmt}"
    m, bars = read_market_bars(root / "data" / "market")
    u, uni = read_universe(root / "data" / "universe")
    f, fund = read_fundamentals(root / "data" / "fundamentals")
    search = root / "mining" / "search"
    ledger = pd.read_csv(search / "ledger.csv")
    loaded[fmt] = {"market_sha": m.content_sha256, "universe_sha": u.content_sha256, "fund_sha": f.content_sha256,
                   "storage": m.storage.get("format"), "rows": len(bars), "bars": bars.reset_index(drop=True),
                   "ledger": ledger, "family": sorted(p.name for p in (search / "factors").glob("*.json"))}
    print(f"{fmt}: storage {m.storage.get('format')}, market rows {len(bars)}, content_sha256 {m.content_sha256[:16]}…, "
          f"universe {u.content_sha256[:12]}…, fundamentals {f.content_sha256[:12]}…, ledger rows {len(ledger)}, family {loaded[fmt]['family']}")
ref = loaded["parquet"]
for fmt in ("csv", "sqlite"):
    x = loaded[fmt]
    for key in ("market_sha", "universe_sha", "fund_sha"):
        if x[key] != ref[key]:
            bad += 1; print(f"FAIL {fmt} {key} differs from parquet")
    try:
        pd.testing.assert_frame_equal(x["bars"], ref["bars"], check_exact=False, rtol=0, atol=0)
        print(f"ok   {fmt} market frame equals parquet frame")
    except AssertionError as exc:
        bad += 1; print(f"FAIL {fmt} market frame differs: {str(exc)[:300]}")
    cols = [c for c in ("expression", "status", "reason", "dev_ic", "selected") if c in x["ledger"].columns]
    try:
        pd.testing.assert_frame_equal(x["ledger"][cols], ref["ledger"][cols])
        print(f"ok   {fmt} search ledger ({cols}) equals parquet's")
    except AssertionError as exc:
        bad += 1; print(f"FAIL {fmt} search ledger differs: {str(exc)[:300]}")
    if x["family"] != ref["family"]:
        bad += 1; print(f"FAIL {fmt} family differs: {x['family']} vs {ref['family']}")
print("RESULT:", "formats agree" if not bad else f"{bad} differences")
sys.exit(1 if bad else 0)
