#!/usr/bin/env python3
"""Edge-input probe (reviewer open-question class "zero volume / trading halt"): one instrument's volume is 0 from
session 60 on while its prices continue. Runs freeze -> export -> invest-eval run on the modified synthetic market and
reports: exit codes, whether daily.csv holds any non-finite value, fills of the halted name after the halt, and the
participation values recorded for it. Usage: <worktree>/.venv/bin/python -I probe_zero_volume_halt.py <worktree> <scratch dir>
Exit 1 on a crash or a non-finite table value, else 0 (informational)."""
import json, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd, pyarrow.parquet as pq
wt = Path(sys.argv[1]).resolve(); S = Path(sys.argv[2]).resolve(); env = dict(os.environ, PATH=f"{wt}/.venv/bin:{os.environ['PATH']}")
def run(*cmd):
    r = subprocess.run(cmd, env=env, cwd=wt, capture_output=True, text=True); return r.returncode, (r.stderr or "")[-1500:]
if S.exists(): shutil.rmtree(S)
S.mkdir(parents=True)
rc, err = run("invest-data", "synthetic", "--out", str(S / "base/data/market"), "--format", "parquet", "--instruments", "20", "--days", "160", "--universe-out", str(S / "base/data/universe"), "--fundamentals-out", str(S / "base/data/fundamentals"))
assert rc == 0, err
sys.path.insert(0, str(wt / "data-pipeline/data-preparation/src")); from invest_data.schemas import publish_market_bars
man = json.loads((S / "base/data/market/manifest.json").read_text()); bars = pq.read_table(S / "base/data/market/data.parquet").to_pandas()
sessions = sorted(bars.date.unique()); halt = sessions[60]; name = sorted(bars.instrument.unique())[1]
bars.loc[(bars.instrument == name) & (bars.date >= halt), "volume"] = 0.0
publish_market_bars(bars.reset_index(drop=True), S / "halt/data/market", dataset_id=man["dataset_id"] + "-halt", metadata=man["metadata"], provenance={"variant": "zero volume from", "date": str(halt), "instrument": name}, fmt="parquet")
cfg = wt / "strategy-evaluation/examples/quantile_long_short.json"; d = S / "halt"; bad = 0
for cmd in (("invest-mine", "freeze", "--expr", "close / delay(close, 5) - 1", "--horizon", "5", "--orientation", "-1", "--out", str(d / "factor.json")),
            ("invest-mine", "export", "--data", str(d / "data/market"), "--universe", str(S / "base/data/universe"), "--factor", str(d / "factor.json"), "--format", "parquet", "--out", str(d / "signals")),
            ("invest-eval", "run", "--data", str(d / "data/market"), "--universe", str(S / "base/data/universe"), "--signals", str(d / "signals"), "--config", str(cfg), "--out", str(d / "eval"))):
    rc, err = run(*cmd); print(f"{cmd[0]} {cmd[1]}: rc {rc}" + (f"\n{err}" if rc else ""))
    if rc: bad += 1; break
if not bad:
    daily = pd.read_csv(d / "eval/tables/daily.csv"); tr = pd.read_csv(d / "eval/tables/trades.csv", dtype={"date": str})
    nonfinite = int((~np.isfinite(daily.drop(columns=["date"]).to_numpy(float))).sum()) - int(daily.benchmark_return.isna().sum())
    print(f"daily rows {len(daily)}, non-finite cells outside benchmark_return NaNs: {nonfinite}; bench NaN sessions {int(daily.benchmark_return.isna().sum())}")
    h = tr[(tr.instrument == name) & (tr.date >= str(halt)[:10])]
    print(f"{name} rows after halt {str(halt)[:10]}: {len(h)}; statuses {h.status.value_counts().to_dict()}; participation {sorted(set(np.round(h.participation.dropna(), 6)))[:5]}; reasons {h.reason.dropna().unique().tolist()[:5]}")
    m = json.loads((d / "eval/metrics.json").read_text()); print("rejected_orders", m["trading"]["rejected_orders"]["value"], "participation_capped_fills", m["trading"]["participation_capped_fills"]["value"], "max_participation", m["trading"]["max_participation"]["value"])
    bad += nonfinite > 0
print("RESULT:", "FAIL" if bad else "PASS (no crash, tables finite)"); sys.exit(1 if bad else 0)
