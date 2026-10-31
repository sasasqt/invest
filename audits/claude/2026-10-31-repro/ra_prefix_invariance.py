#!/usr/bin/env python3
"""Executed prefix-invariance check (repo audit 2026-10-31, step 6 "Timing").

Usage: <worktree>/.venv/bin/python -I ra_prefix_invariance.py <worktree> <scratch dir> [T_INDEX=199] [INSTRUMENTS=20] [DAYS=300]

1. invest-data synthetic publishes a market (seeded, deterministic) plus universe and fundamentals under <scratch>/base.
2. Two more markets are published from the same bars: "cut" keeps only sessions <= T; "perturbed" keeps every session but
   multiplies open/high/low/close(/close_as_traded) after T by a seeded log-normal factor and volume by a seeded uniform factor.
3. For each of the three markets the same frozen factor (invest-mine freeze, expression close / delay(close, 5) - 1, horizon 5,
   orientation -1) is exported to signals and evaluated with the example config (invest-eval run), the universe shared.
4. Compared, for the three runs: signals with decision_date <= T minus the horizon (5 sessions); trades (fills) and daily rows dated
   before T. They must be identical: a signal, eligibility decision or fill dated at or before T may not depend on bars after T.
   Rows dated exactly T are reported separately (a market cut at T ends there, so the cut run may close positions on T).
Exit 1 when any prefix differs. Writes nothing outside <scratch dir>.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd, pyarrow.parquet as pq

wt = Path(sys.argv[1]).resolve(); S = Path(sys.argv[2]).resolve(); TI = int(sys.argv[3]) if len(sys.argv) > 3 else 199
INS = sys.argv[4] if len(sys.argv) > 4 else "20"; DAYS = sys.argv[5] if len(sys.argv) > 5 else "300"
env = dict(os.environ, PATH=f"{wt}/.venv/bin:{os.environ['PATH']}")
def run(*cmd):
    r = subprocess.run(cmd, env=env, cwd=wt, capture_output=True, text=True)
    if r.returncode: print("COMMAND FAILED", cmd, r.stderr[-2000:]); sys.exit(2)
if S.exists(): shutil.rmtree(S)
S.mkdir(parents=True)
base = S / "base"
run("invest-data", "synthetic", "--out", str(base / "data/market"), "--format", "parquet", "--instruments", INS, "--days", DAYS, "--universe-out", str(base / "data/universe"), "--fundamentals-out", str(base / "data/fundamentals"))
man = json.loads((base / "data/market/manifest.json").read_text()); bars = pq.read_table(base / "data/market/data.parquet").to_pandas()
sessions = sorted(bars.date.unique()); T = sessions[TI]; print(f"sessions {len(sessions)}, T = {T} (index {TI}), bars {len(bars)}")
sys.path.insert(0, str(wt / "data-pipeline/data-preparation/src"))
from invest_data.schemas import publish_market_bars  # writer only; the behaviour under test is downstream
cut = bars[bars.date <= T].copy()
rng = np.random.default_rng(1); pert = bars.copy(); after = (pert.date > T).to_numpy()
fac = np.exp(rng.normal(0, 0.02, after.sum()))
for c in ("open", "high", "low", "close", "close_as_traded"):
    if c in pert: pert.loc[after, c] = pert.loc[after, c].to_numpy() * fac
pert.loc[after, "volume"] = np.round(pert.loc[after, "volume"].to_numpy() * rng.uniform(0.5, 1.5, after.sum()))
for name, frame in (("cut", cut), ("perturbed", pert)):
    publish_market_bars(frame.reset_index(drop=True), S / name / "data/market", dataset_id=f"{man['dataset_id']}-{name}", metadata=man["metadata"], provenance={"derived_from": man["content_sha256"], "variant": name, "T": str(T)}, fmt="parquet")
cfg = wt / "strategy-evaluation/examples/quantile_long_short.json"
for name in ("base", "cut", "perturbed"):
    d = S / name
    run("invest-mine", "freeze", "--expr", "close / delay(close, 5) - 1", "--horizon", "5", "--orientation", "-1", "--out", str(d / "factor.json"))
    run("invest-mine", "export", "--data", str(d / "data/market"), "--universe", str(base / "data/universe"), "--factor", str(d / "factor.json"), "--format", "parquet", "--out", str(d / "signals"))
    run("invest-eval", "run", "--data", str(d / "data/market"), "--universe", str(base / "data/universe"), "--signals", str(d / "signals"), "--config", str(cfg), "--out", str(d / "eval"))
Tm5 = sessions[TI - 5]; fails = 0
def load(name):
    d = S / name; sig = pq.read_table(d / "signals/data.parquet").to_pandas(); sig["decision_date"] = sig.decision_date.astype(str)
    tr = pd.read_csv(d / "eval/tables/trades.csv", dtype={"date": str, "decision_date": str}); dy = pd.read_csv(d / "eval/tables/daily.csv", dtype={"date": str}); return sig, tr, dy
ref = load("base"); Ts = str(T); Tm5s = str(Tm5)
for name in ("cut", "perturbed"):
    sig, tr, dy = load(name)
    a = ref[0][ref[0].decision_date <= Tm5s].sort_values(["decision_date", "instrument"]).reset_index(drop=True); b = sig[sig.decision_date <= Tm5s].sort_values(["decision_date", "instrument"]).reset_index(drop=True)
    same = a.shape == b.shape and (a.decision_date.tolist() == b.decision_date.tolist()) and (a.instrument.tolist() == b.instrument.tolist()) and np.array_equal(a.score.to_numpy(), b.score.to_numpy())
    print(("PASS" if same else "FAIL"), f"signals <= T-5 ({Tm5s}) identical base vs {name}: rows {len(a)} vs {len(b)}"); fails += not same
    a = ref[1][ref[1].date < Ts].sort_values(["date", "instrument"]).reset_index(drop=True); b = tr[tr.date < Ts].sort_values(["date", "instrument"]).reset_index(drop=True)
    same = a.shape == b.shape and all(a[c].tolist() == b[c].tolist() for c in ("date", "instrument", "status", "decision_date")) and all(np.allclose(a[c].astype(float), b[c].astype(float), rtol=0, atol=0, equal_nan=True) for c in ("shares", "price", "notional", "commission", "spread", "impact", "participation"))
    print(("PASS" if same else "FAIL"), f"fills dated < T identical base vs {name}: rows {len(a)} vs {len(b)}"); fails += not same
    a = ref[2][ref[2].date < Ts].reset_index(drop=True); b = dy[dy.date < Ts].reset_index(drop=True)
    def eq(x, y):
        x, y = x.to_numpy(), y.to_numpy()
        return np.array_equal(x, y, equal_nan=True) if x.dtype.kind == "f" and y.dtype.kind == "f" else np.array_equal(x, y)
    same = a.shape == b.shape and all(eq(a[c], b[c]) for c in a.columns)
    diffcols = [c for c in a.columns if a.shape == b.shape and not eq(a[c], b[c])]
    print(("PASS" if same else "FAIL"), f"daily rows dated < T identical base vs {name}: rows {len(a)} vs {len(b)}; differing columns {diffcols}"); fails += not same
    at = ref[1][ref[1].date == Ts]; bt = tr[tr.date == Ts]; print("INFO", f"fills dated T: base {len(at)} vs {name} {len(bt)}; signals dated in (T-5, T]: base {int(((ref[0].decision_date > Tm5s) & (ref[0].decision_date <= Ts)).sum())} vs {name} {int(((sig.decision_date > Tm5s) & (sig.decision_date <= Ts)).sum())}")
print(f"TOTAL FAIL={fails}"); sys.exit(1 if fails else 0)
