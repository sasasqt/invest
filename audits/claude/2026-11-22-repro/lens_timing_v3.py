"""Timing lens v3 (2026-11-22): v2 of 2026-11-15 with the family sub-check repaired.

v2 compared config.json["family"], a key the search never writes (cli.py:485-489 writes the family only as
ledger.csv selected rows and factors/*.json), so that sub-check compared None with None and always passed.
v3 compares the selected (expression, orientation) pairs of ledger.csv and the factors/*.json expressions.

Original description (v2), a variant of 2026-11-08's prefix-invariance check (open place 5 of the 2026-11-08 reviewer 2).

Publish the synth-M market, universe and fundamentals bundles three ways and run search -> export -> eval on each with the
same explicit confirmation start: full; cut at T (bars and fundamentals known by T only, memberships still open at T left
open); shocked after T (OHLC, close_as_traded and volume perturbed with a fixed seed; one instrument stops trading 10
sessions after T; one membership ends 15 sessions after T; every fundamentals value published after T perturbed, each with
a later revision, plus a late revision of a pre-T period published after T). Every signal, eval daily row, trade and the
search's selected family dated at or before T must be identical in all three runs (DATA_CONTRACT.md: point-in-time
membership and fundamentals usable from the close of available_date; signals use only information available at the
decision date's close).
Usage: python lens_timing_v2.py <synth-M out dir> <work dir> <T YYYY-MM-DD> <confirm-start YYYY-MM-DD> <config json> <bin dir>
Exit 0 when prefix-invariant, 1 when a prefix differs, 2 on setup error. Report only: writes under <work dir>.
"""
from __future__ import annotations
import json
import os, shutil, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from invest_data.schemas import publish_fundamentals, publish_market_bars, publish_universe, read_fundamentals, read_market_bars, read_universe

src, work, T, confirm_start, config, bindir = sys.argv[1:7]
src, work = Path(src), Path(work)
if os.environ.get("COMPARE_ONLY") != "1":
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True)
T_ts = pd.Timestamp(T)
m_man, bars = read_market_bars(src / "data" / "market"); u_man, uni = read_universe(src / "data" / "universe"); f_man, fund = read_fundamentals(src / "data" / "fundamentals")
bars, uni, fund = bars.copy(), uni.copy(), fund.copy()
sessions = pd.DatetimeIndex(sorted(bars["date"].unique()))
after_T = sessions[sessions > T_ts]
rng = np.random.default_rng(20261115)
names = sorted(bars["instrument"].unique())
stopper, leaver = names[2], names[5]
# cut
cut_bars = bars[bars["date"] <= T_ts].copy()
cut_uni = uni[uni["start_date"] <= T_ts].copy(); cut_uni.loc[cut_uni["end_date"] > T_ts, "end_date"] = pd.NaT
cut_fund = fund[fund["available_date"] <= T_ts].copy()
# shocked
after = bars["date"] > T_ts
sh_bars = bars.copy(); n_after = int(after.sum())
f = rng.uniform(0.8, 1.2, size=n_after)
for col in ("open", "high", "low", "close"): sh_bars.loc[after, col] = sh_bars.loc[after, col].to_numpy() * f
sh_bars.loc[after, "close_as_traded"] = sh_bars.loc[after, "close_as_traded"].to_numpy() * rng.uniform(0.5, 2.0, size=n_after)
sh_bars.loc[after, "volume"] = sh_bars.loc[after, "volume"].to_numpy() * rng.uniform(0.5, 1.5, size=n_after)
stop_after = after_T[min(10, len(after_T) - 1)]
sh_bars = sh_bars[~((sh_bars["instrument"] == stopper) & (sh_bars["date"] > stop_after))].copy()
sh_uni = uni.copy(); leave_on = after_T[min(15, len(after_T) - 1)]
row = (sh_uni["instrument"] == leaver) & (sh_uni["end_date"].isna() | (sh_uni["end_date"] > leave_on))
sh_uni.loc[row, "end_date"] = leave_on
sh_fund = fund.copy(); late = sh_fund["available_date"] > T_ts
sh_fund.loc[late, "value"] = sh_fund.loc[late, "value"].to_numpy() * 1.3
revisions = sh_fund[late].copy(); revisions["available_date"] = revisions["available_date"] + pd.Timedelta(days=20); revisions["value"] = revisions["value"] * 0.7
old = fund[fund["available_date"] <= T_ts].sort_values("period_end").iloc[[-1]].copy()  # a pre-T period revised after T
old["available_date"] = after_T[min(3, len(after_T) - 1)]; old["value"] = old["value"] * 10 + 5
sh_fund = pd.concat([sh_fund, revisions, old], ignore_index=True).drop_duplicates(["instrument", "field", "period_end", "available_date"])
variants = {"full": (bars, uni, fund), "cut": (cut_bars, cut_uni, cut_fund), "shocked": (sh_bars, sh_uni, sh_fund)}
print(f"T={T} sessions after T {len(after_T)}; stopper {stopper} stops after {stop_after.date()}, leaver {leaver} leaves {leave_on.date()}; fundamentals rows full {len(fund)} cut {len(cut_fund)} shocked {len(sh_fund)} ({int(late.sum())} perturbed, {len(revisions)} revisions, 1 late revision of {old['period_end'].iloc[0].date()}); bars full {len(bars)} cut {len(cut_bars)} shocked {len(sh_bars)}")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("setup error:", " ".join(map(str, cmd)), "\n", r.stdout[-2000:], r.stderr[-2000:]); sys.exit(2)

for name, (b, u, fd) in ({} if os.environ.get("COMPARE_ONLY") == "1" else variants).items():  # COMPARE_ONLY=1 reuses published variants
    v = work / name; market, universe, fundamentals = v / "data" / "market", v / "data" / "universe", v / "data" / "fundamentals"
    publish_market_bars(b, market, dataset_id=f"{m_man.dataset_id}-{name}", metadata=dict(m_man.metadata), provenance=dict(m_man.provenance), fmt="parquet")
    publish_universe(u, universe, dataset_id=f"{u_man.dataset_id}-{name}", provenance=dict(u_man.provenance))
    publish_fundamentals(fd, fundamentals, dataset_id=f"{f_man.dataset_id}-{name}", provenance=dict(f_man.provenance))
    run([f"{bindir}/invest-mine", "search", "--data", market, "--universe", universe, "--fundamentals", fundamentals, "--trials", "200", "--confirm-start", confirm_start, "--ledger", v / "mining" / "ledger.jsonl", "--out", v / "mining" / "search"])
    run([f"{bindir}/invest-mine", "export", "--data", market, "--universe", universe, "--fundamentals", fundamentals, "--from-search", v / "mining" / "search", "--format", "parquet", "--out", v / "signals"])
    run([f"{bindir}/invest-eval", "run", "--data", market, "--universe", universe, "--signals", v / "signals", "--config", config, "--out", v / "eval"])
    print(f"published and evaluated {name}")

def load(name):
    v = work / name
    sig = pd.read_parquet(v / "signals" / "data.parquet"); sig["decision_date"] = pd.to_datetime(sig["decision_date"])
    sig = sig[sig["decision_date"] <= T_ts].sort_values(["decision_date", "instrument"]).reset_index(drop=True)
    daily = pd.read_csv(v / "eval" / "tables" / "daily.csv", parse_dates=["date"]); daily = daily[daily["date"] <= T_ts].reset_index(drop=True)
    trades = pd.read_csv(v / "eval" / "tables" / "trades.csv", parse_dates=["date"]); trades = trades[trades["date"] <= T_ts].sort_values(["date", "instrument"]).reset_index(drop=True)
    ledger = pd.read_csv(v / "mining" / "search" / "ledger.csv")
    sel = ledger[ledger["selected"].astype(str).str.lower() == "true"]
    fam = {"selected": sorted(zip(sel["expression"].astype(str), sel["orientation"].astype(int))),
           "factor_files": sorted(json.loads(p.read_text(encoding="utf-8"))["expression"] for p in (v / "mining" / "search" / "factors").glob("*.json"))}
    return sig, daily, trades, fam, ledger

full = load("full"); bad = 0
print(f"full: signals<=T {len(full[0])}, daily rows<=T {len(full[1])}, trades<=T {len(full[2])}, family {full[3]['selected'][:5]} ({len(full[3]['selected'])} selected, {len(full[3]['factor_files'])} factor files), ledger rows {len(full[4])}")
for name in ("cut", "shocked"):
    other = load(name)
    for label, a, b in (("signals", full[0], other[0]), ("eval daily rows", full[1], other[1]), ("trades", full[2], other[2])):
        if a.shape != b.shape:
            print(f"DIFF {name} {label}: shape {a.shape} vs {b.shape}"); bad += 1; continue
        num = a.select_dtypes("number"); diff = ~np.isclose(num.to_numpy(dtype=float), b[num.columns].to_numpy(dtype=float), rtol=0, atol=0, equal_nan=True)
        obj = a.drop(columns=num.columns).astype(object).fillna("<NA>").astype(str); odiff = (obj.to_numpy() != b[obj.columns].astype(object).fillna("<NA>").astype(str).to_numpy())  # pandas 3 StringDtype keeps NaN through astype(str); compare missing as equal
        n = int(diff.sum() + odiff.sum())
        print(f"{'ok  ' if n == 0 else 'DIFF'} {name} {label}: {n} differing cells of {a.size}")
        bad += n > 0
    if not full[3]["selected"]: print("setup error: full run selected no family, the family check would be vacuous"); sys.exit(2)
    same_family = full[3] == other[3]; print(f"{'ok  ' if same_family else 'DIFF'} {name} selected family identical: {same_family}")
    bad += not same_family
    dev = full[4].merge(other[4], on=["expression"], how="inner", suffixes=("_full", f"_{name}")) if "expression" in full[4].columns else None
    print(f"info {name}: ledger rows {len(other[4])} (full {len(full[4])}); confirmation window end differs by design")
print("RESULT:", "prefix-invariant" if not bad else f"PREFIX DIFFERS ({bad} tables)")
sys.exit(1 if bad else 0)
