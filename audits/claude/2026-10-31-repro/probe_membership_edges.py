#!/usr/bin/env python3
"""Edge-input probe (reviewer 2's open place 1, repo audit 2026-10-31): universe membership edges without bars.
One synthetic market (20 instruments, 160 sessions), three edits:
 (a) late listing: L is a member from the first session but its first bar is session 10;
 (b) exit on a no-bar session: E's membership ends at session 80 (end_date, exclusive) and E has no bars on sessions 77-79;
 (c) mid-membership halt: H has no bars on sessions 40-42 and stays a member.
Runs freeze -> export -> invest-eval run, then recomputes the universe equal-weight benchmark independently from the bars and the
universe bundle with the documented rules (strategy-evaluation/README.md: members at the previous close; universe interval
start_date <= date < end_date; a missing price invalidates that session and the following return, no forward fill; NaN when no held
name has a return) and compares it with tables/daily.csv benchmark_return (rtol 1e-9, NaN equals NaN). Also checks: no crash,
finite tables outside the documented benchmark NaNs, no fill of L before its first bar, no signal of L before its first bar.
Usage: <worktree>/.venv/bin/python -I probe_membership_edges.py <worktree> <scratch dir>
Exit 1 on a crash, a non-finite table value, a benchmark mismatch or an impossible fill; else 0."""
import datetime as dt, json, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd, pyarrow.parquet as pq
wt = Path(sys.argv[1]).resolve(); S = Path(sys.argv[2]).resolve(); env = dict(os.environ, PATH=f"{wt}/.venv/bin:{os.environ['PATH']}")
def run(*cmd):
    r = subprocess.run(cmd, env=env, cwd=wt, capture_output=True, text=True); return r.returncode, (r.stderr or "")[-1500:]
if S.exists(): shutil.rmtree(S)
S.mkdir(parents=True)
rc, err = run("invest-data", "synthetic", "--out", str(S / "base/data/market"), "--format", "parquet", "--instruments", "20", "--days", "160", "--universe-out", str(S / "base/data/universe"), "--fundamentals-out", str(S / "base/data/fundamentals"))
assert rc == 0, err
sys.path.insert(0, str(wt / "data-pipeline/data-preparation/src")); from invest_data.schemas import publish_market_bars, publish_universe
man = json.loads((S / "base/data/market/manifest.json").read_text()); bars = pq.read_table(S / "base/data/market/data.parquet").to_pandas()
bars["date"] = pd.to_datetime(bars["date"]); cal = sorted(bars.date.unique()); names = sorted(bars.instrument.unique())
L, E, H = names[2], names[3], names[4]
drop = ((bars.instrument == L) & (bars.date < cal[10])) | ((bars.instrument == E) & bars.date.isin(cal[77:80])) | ((bars.instrument == H) & bars.date.isin(cal[40:43]))
bars2 = bars[~drop].reset_index(drop=True); print(f"bars {len(bars)} -> {len(bars2)} (L={L} first bar {cal[10].date()}, E={E} no bars {cal[77].date()}..{cal[79].date()} end {cal[80].date()}, H={H} halt {cal[40].date()}..{cal[42].date()})")
d = S / "edges"
publish_market_bars(bars2, d / "data/market", dataset_id=man["dataset_id"] + "-edges", metadata=man["metadata"], provenance={"variant": "membership edges without bars"}, fmt="parquet")
uni = pd.DataFrame({"universe": "SYN", "instrument": names, "start_date": [cal[0].date()] * len(names), "end_date": [cal[80].date() if n == E else None for n in names]})
publish_universe(uni, d / "data/universe", dataset_id="syn-universe-edges", fmt="parquet")
cfg = wt / "strategy-evaluation/examples/quantile_long_short.json"; bad = 0
for cmd in (("invest-mine", "freeze", "--expr", "close / delay(close, 5) - 1", "--horizon", "5", "--orientation", "-1", "--out", str(d / "factor.json")),
            ("invest-mine", "export", "--data", str(d / "data/market"), "--universe", str(d / "data/universe"), "--factor", str(d / "factor.json"), "--format", "parquet", "--out", str(d / "signals")),
            ("invest-eval", "run", "--data", str(d / "data/market"), "--universe", str(d / "data/universe"), "--signals", str(d / "signals"), "--config", str(cfg), "--out", str(d / "eval"))):
    rc, err = run(*cmd); print(f"{cmd[0]} {cmd[1]}: rc {rc}" + (f"\n{err}" if rc else ""))
    if rc: bad += 1; break
if not bad:
    daily = pd.read_csv(d / "eval/tables/daily.csv"); daily["date"] = pd.to_datetime(daily["date"]); tr = pd.read_csv(d / "eval/tables/trades.csv"); tr["date"] = pd.to_datetime(tr["date"])
    sig = pq.read_table(d / "signals/data.parquet").to_pandas(); sig["date"] = pd.to_datetime(sig[next(c for c in sig.columns if "date" in c)])
    nonfinite = int((~np.isfinite(daily.drop(columns=["date"]).to_numpy(float))).sum()) - int(daily.benchmark_return.isna().sum())
    print(f"daily rows {len(daily)} ({daily.date.iloc[0].date()}..{daily.date.iloc[-1].date()}); non-finite cells outside benchmark_return NaNs: {nonfinite}; benchmark NaN sessions {int(daily.benchmark_return.isna().sum())}")
    bad += nonfinite > 0
    # independent benchmark: documented rules only
    close = bars2.pivot(index="date", columns="instrument", values="close").reindex(index=cal, columns=names)
    rets = close / close.shift(1) - 1
    member = pd.DataFrame(False, index=cal, columns=names)
    for r in uni.itertuples():
        start = pd.Timestamp(r.start_date); end = pd.Timestamp(r.end_date) if r.end_date is not None else None
        member.loc[[c for c in cal if c >= start and (end is None or c < end)], r.instrument] = True
    held = member.shift(1); held.iloc[0] = member.iloc[0]; held = held.astype(bool)
    bench = rets.where(held).mean(axis=1)
    got = daily.set_index("date")["benchmark_return"]; exp = bench.reindex(got.index)
    both_nan = got.isna() & exp.isna(); close_ok = np.isclose(got.to_numpy(float), exp.to_numpy(float), rtol=1e-9, atol=1e-12)
    mism = got.index[~(both_nan.to_numpy() | close_ok)]
    print(f"benchmark_return vs independent recomputation: {len(got)} sessions, {len(mism)} mismatches" + (f": {[(str(i.date()), float(got[i]), float(exp[i])) for i in mism[:5]]}" if len(mism) else ""))
    bad += len(mism) > 0
    for lab, inst, days in (("H halt", H, cal[40:44]), ("E exit", E, cal[76:82]), ("L listing", L, cal[9:12])):
        print(f"  {lab} {inst}: own rets {[None if np.isnan(rets.loc[c, inst]) else round(float(rets.loc[c, inst]), 5) for c in days]} held {[bool(held.loc[c, inst]) for c in days]} on {days[0].date()}..{days[-1].date()}")
    filledL = tr[(tr.instrument == L) & (tr.date < cal[10]) & (tr.status == "filled")]
    sigL = sig[(sig.instrument == L) & (sig.date < cal[10])]
    print(f"L before first bar: fills {len(filledL)} (expected 0), signals {len(sigL)} (expected 0); L rows in trades by status {tr[tr.instrument == L].status.value_counts().to_dict()}")
    bad += len(filledL) > 0 or len(sigL) > 0
    e_rows = tr[(tr.instrument == E) & (tr.date >= cal[75])]
    print(f"E from {cal[75].date()}: trade rows {len(e_rows)}: " + "; ".join(f"{r.date.date()} {r.status}{(' ' + str(r.reason)) if isinstance(r.reason, str) else ''}" for r in e_rows.itertuples()))
    h_rows = tr[(tr.instrument == H) & (tr.date >= cal[39]) & (tr.date <= cal[45])]
    print(f"H around the halt: " + ("; ".join(f"{r.date.date()} {r.status}{(' ' + str(r.reason)) if isinstance(r.reason, str) else ''}" for r in h_rows.itertuples()) or "no trade rows"))
    m = json.loads((d / "eval/metrics.json").read_text()); print("benchmark_total_return", m["benchmark"]["benchmark_total_return"]["value"] if "benchmark" in m and "benchmark_total_return" in m["benchmark"] else "n/a", "rejected_orders", m["trading"]["rejected_orders"]["value"])
print("RESULT:", "FAIL" if bad else "PASS (no crash, tables finite, benchmark matches the documented rules, no impossible fill)"); sys.exit(1 if bad else 0)
