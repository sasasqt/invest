"""Timing lens: executed prefix invariance.

Publish the synth-M market bundle three ways: full, cut after T, and perturbed after T (fixed seed), run search -> export -> eval on each
with the same explicit confirmation start, and require every signal, eval daily row and trade dated at or before T to be identical.
Usage: python lens_timing.py <synth-M out dir> <work dir> <T YYYY-MM-DD> <confirm-start YYYY-MM-DD> <config json> <bin dir>
Exit 0 when prefix-invariant, 1 when a prefix differs, 2 on setup error. Report only: writes under <work dir>.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from invest_data.schemas import publish_market_bars, read_market_bars

src, work, T, confirm_start, config, bindir = sys.argv[1:7]
src, work = Path(src), Path(work)
if work.exists():
    shutil.rmtree(work)
work.mkdir(parents=True)
T_ts = pd.Timestamp(T)
manifest, bars = read_market_bars(src / "data" / "market")
bars = bars.copy()
bars["date"] = pd.to_datetime(bars["date"])
after = bars["date"] > T_ts
rng = np.random.default_rng(20261108)
shocked = bars.copy()
factor = rng.uniform(0.8, 1.2, size=int(after.sum()))
for col in ("open", "high", "low", "close"):
    shocked.loc[after, col] = shocked.loc[after, col].to_numpy() * factor
shocked.loc[after, "volume"] = shocked.loc[after, "volume"].to_numpy() * rng.uniform(0.5, 1.5, size=int(after.sum()))
variants = {"full": bars, "cut": bars[~after].copy(), "shocked": shocked}
print(f"rows full {len(bars)} cut {len(variants['cut'])} shocked {len(shocked)}; T={T}; after-T rows {int(after.sum())}")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("setup error:", " ".join(cmd), "\n", r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(2)


for name, frame in variants.items():
    v = work / name
    market = v / "data" / "market"
    publish_market_bars(frame, market, dataset_id=f"{manifest.dataset_id}-{name}", metadata=dict(manifest.metadata),
                        provenance=dict(manifest.provenance), fmt="parquet")
    universe = str(src / "data" / "universe")
    run([f"{bindir}/invest-mine", "search", "--data", str(market), "--universe", universe, "--trials", "200",
         "--confirm-start", confirm_start, "--ledger", str(v / "mining" / "ledger.jsonl"), "--out", str(v / "mining" / "search")])
    run([f"{bindir}/invest-mine", "export", "--data", str(market), "--universe", universe, "--from-search", str(v / "mining" / "search"),
         "--format", "parquet", "--out", str(v / "signals")])
    run([f"{bindir}/invest-eval", "run", "--data", str(market), "--universe", universe, "--signals", str(v / "signals"),
         "--config", config, "--out", str(v / "eval")])
    print(f"published and evaluated {name}")


def load(name: str):
    v = work / name
    sig = pd.read_parquet(v / "signals" / "data.parquet")
    sig["decision_date"] = pd.to_datetime(sig["decision_date"])
    sig = sig[sig["decision_date"] <= T_ts].sort_values(["decision_date", "instrument"]).reset_index(drop=True)
    daily = pd.read_csv(v / "eval" / "tables" / "daily.csv", parse_dates=["date"])
    daily = daily[daily["date"] <= T_ts].reset_index(drop=True)
    trades = pd.read_csv(v / "eval" / "tables" / "trades.csv", parse_dates=["date"])
    trades = trades[trades["date"] <= T_ts].sort_values(["date", "instrument"]).reset_index(drop=True)
    fam = json.loads((v / "mining" / "search" / "config.json").read_text(encoding="utf-8"))
    return sig, daily, trades, fam


full = load("full")
bad = 0
for name in ("cut", "shocked"):
    other = load(name)
    for label, a, b in (("signals", full[0], other[0]), ("eval daily rows", full[1], other[1]), ("trades", full[2], other[2])):
        try:
            pd.testing.assert_frame_equal(a, b, check_exact=True)
            print(f"ok   {label} on/before {T} identical: full vs {name} ({len(a)} rows)")
        except AssertionError as exc:
            bad += 1
            print(f"FAIL {label} on/before {T} differ: full vs {name} ({len(a)} vs {len(b)} rows): {str(exc)[:300]}")
    print(f"     split full {full[3]['split']['confirmation']} vs {name} {other[3]['split']['confirmation']}")
print("RESULT:", "prefix-invariant" if not bad else f"{bad} prefix differences")
sys.exit(1 if bad else 0)
