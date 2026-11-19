"""Compare Yahoo CLI outputs: original (out_YO) vs Y1 (after-T perturbation, exact) and
Y2 (pre-T rescale by a later corporate action; equal up to floating-point rounding).

Usage: python compare_y.py <yahoo dir> <T>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from invest_data.schemas import read_signals

root, T = Path(sys.argv[1]), pd.Timestamp(sys.argv[2])
exprs = [e for e in (root / "exprs.txt").read_text().splitlines() if e]
problems = 0
H = 5


def report(what: str, bad: int, total: int, detail: str = "") -> None:
    global problems
    if bad:
        problems += 1
        print(f"DIFF {what}: {bad} of {total} differ {detail}")
    else:
        print(f"same {what}: {total} compared")


def cmp_num(a: pd.Series, b: pd.Series, rtol: float, atol: float) -> int:
    x, y = a.to_numpy(float), b.to_numpy(float)
    return int((~np.isclose(x, y, rtol=rtol, atol=atol, equal_nan=True)).sum())


o = root / "out_YO"
for tag, rtol, atol in (("Y1", 0.0, 0.0), ("Y2", 1e-9, 1e-12)):
    p = root / f"out_{tag}"
    print(f"== {tag} (rtol {rtol})")
    for i, expr in enumerate(exprs, start=1):
        _, so = read_signals(o / f"sig{i}")
        _, sp = read_signals(p / f"sig{i}")
        key = ["decision_date", "instrument"]
        so = so[so["decision_date"] <= T].sort_values(key).reset_index(drop=True)
        sp = sp[sp["decision_date"] <= T].sort_values(key).reset_index(drop=True)
        if so[key].astype(str).equals(sp[key].astype(str)) is False:
            report(f"signal keys <= T {expr!r}", 1, len(so), f"({len(so)} vs {len(sp)} rows)")
            continue
        bad = cmp_num(so["score"], sp["score"], rtol, atol)
        ro = so.groupby("decision_date")["score"].rank(method="average")
        rp = sp.groupby("decision_date")["score"].rank(method="average")
        report(f"signals <= T {expr!r} (values)", bad, len(so))
        report(f"signals <= T {expr!r} (per-date ranks)", int((ro != rp).sum()), len(so))
    for k in (len(exprs) + 1, len(exprs) + 2):
        for table in ("daily_ic.csv", "quantile_returns.csv"):
            a = pd.read_csv(o / f"diag{k}" / "tables" / table, parse_dates=[0])
            b = pd.read_csv(p / f"diag{k}" / "tables" / table, parse_dates=[0])
            pos = int((a.iloc[:, 0] <= T).sum()) - 1
            cutoff = a.iloc[pos - 1 - H, 0]
            a, b = a[a.iloc[:, 0] <= cutoff], b[b.iloc[:, 0] <= cutoff]
            bad = sum(cmp_num(a[c], b[c], max(rtol, 1e-12), atol) for c in a.columns[1:])
            report(f"diag{k} {table} (labels known by T)", bad, a.size)
    a = pd.read_csv(o / "eval" / "tables" / "daily.csv", parse_dates=["date"])
    b = pd.read_csv(p / "eval" / "tables" / "daily.csv", parse_dates=["date"])
    a, b = a[a["date"] <= T], b[b["date"] <= T]
    cols = [
        "equity",
        "cash",
        "traded_notional",
        "commission_cost",
        "spread_cost",
        "impact_cost",
        "borrow_cost",
        "n_rejected",
        "n_clipped",
        "return",
        "gross_return",
        "benchmark_return",
    ]
    report(
        "eval daily.csv <= T",
        sum(cmp_num(a[c], b[c], max(rtol, 1e-12), 1e-6) for c in cols),
        len(a) * len(cols),
    )
    a = pd.read_csv(o / "eval" / "tables" / "trades.csv", parse_dates=["date"])
    b = pd.read_csv(p / "eval" / "tables" / "trades.csv", parse_dates=["date"])
    a, b = a[a["date"] <= T], b[b["date"] <= T]
    cols = ["notional", "commission", "spread", "impact", "participation"]
    report(
        "eval trades.csv <= T",
        sum(cmp_num(a[c], b[c], max(rtol, 1e-12), 1e-6) for c in cols),
        len(a) * len(cols),
    )
    for table, col in (("memberships.csv.gz", "decision_date"), ("daily_returns.csv.gz", "date")):
        a = pd.read_csv(o / "quant" / "tables" / table, parse_dates=[col])
        b = pd.read_csv(p / "quant" / "tables" / table, parse_dates=[col])
        a, b = a[a[col] <= T], b[b[col] <= T]
        num = [c for c in a.columns if c not in (col, "instrument")]
        report(
            f"quantiles {table} <= T",
            sum(cmp_num(a[c], b[c], max(rtol, 1e-12), 1e-12) for c in num),
            a.size,
        )
print("PROBLEMS:", problems)
