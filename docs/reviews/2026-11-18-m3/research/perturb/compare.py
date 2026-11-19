"""Compare CLI outputs on original vs perturbed-after-T bundles: nothing at or before T may differ.

Usage: python compare.py <outO> <outP> <T> [<outPO>]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from invest_data.schemas import read_signals

o, p, T = Path(sys.argv[1]), Path(sys.argv[2]), pd.Timestamp(sys.argv[3])
po = Path(sys.argv[4]) if len(sys.argv) > 4 else None
exprs = [e for e in (Path(__file__).parent / "exprs.txt").read_text().splitlines() if e]
problems = 0


def same(a: pd.DataFrame, b: pd.DataFrame, what: str) -> None:
    global problems
    a = a.reset_index(drop=True)
    b = b.reset_index(drop=True)
    if a.shape != b.shape:
        problems += 1
        print(f"DIFF {what}: shape {a.shape} vs {b.shape}")
        return
    num = a.select_dtypes("number").columns
    other = [c for c in a.columns if c not in num]
    bad_num = ~np.isclose(
        a[num].to_numpy(float), b[num].to_numpy(float), rtol=1e-12, atol=0, equal_nan=True
    )
    bad_other = (
        a[other].astype(object).fillna("<NA>").astype(str)
        != b[other].astype(object).fillna("<NA>").astype(str)
    ).to_numpy()
    n = int(bad_num.sum() + bad_other.sum())
    if n:
        problems += 1
        rows = np.flatnonzero(bad_num.any(axis=1) | bad_other.any(axis=1))[:3]
        print(f"DIFF {what}: {n} cells differ; first rows:\n{a.iloc[rows]}\n{b.iloc[rows]}")
    else:
        print(f"same {what}: {len(a)} rows")


for i, expr in enumerate(exprs, start=1):
    _, so = read_signals(o / f"sig{i}")
    _, sp = read_signals(p / f"sig{i}")
    key = ["decision_date", "instrument"]
    so = so[so["decision_date"] <= T].sort_values(key)
    sp = sp[sp["decision_date"] <= T].sort_values(key)
    same(so, sp, f"signals <= T for {expr!r}")

# Diagnostics: daily IC rows whose label interval [t+1, t+1+h] ends at or before T.
h = 5
for k in (len(exprs) + 1, len(exprs) + 2):
    for table in ("daily_ic.csv", "quantile_returns.csv"):
        a = pd.read_csv(o / f"diag{k}" / "tables" / table, parse_dates=[0])
        b = pd.read_csv(p / f"diag{k}" / "tables" / table, parse_dates=[0])
        sessions = a.iloc[:, 0]
        pos_T = int((sessions <= T).sum()) - 1
        cutoff = sessions.iloc[pos_T - 1 - h]  # t + 1 + h <= T
        same(
            a[a.iloc[:, 0] <= cutoff],
            b[b.iloc[:, 0] <= cutoff],
            f"diag{k} {table} labels known by T",
        )

for name, other in (("P signals", p), ("O signals on P", po)):
    if other is None:
        continue
    for table, col in (("daily.csv", "date"), ("trades.csv", "date")):
        a = pd.read_csv(o / "eval" / "tables" / table, parse_dates=[col])
        b = pd.read_csv(other / "eval" / "tables" / table, parse_dates=[col])
        same(a[a[col] <= T], b[b[col] <= T], f"eval {table} <= T ({name})")
    for table, col in (("memberships.csv.gz", "decision_date"), ("daily_returns.csv.gz", "date")):
        a = pd.read_csv(o / "quant" / "tables" / table, parse_dates=[col])
        b = pd.read_csv(other / "quant" / "tables" / table, parse_dates=[col])
        same(a[a[col] <= T], b[b[col] <= T], f"quantiles {table} <= T ({name})")

print("PROBLEMS:", problems)
