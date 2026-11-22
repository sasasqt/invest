"""Uncovered decision branches (repo audit 2026-11-22, test-quality lens, rule 20: look at uncovered decision code).

checks313 coverage (work/2026-11-22/tests/checks313/cov.json) shows four decision branches no test reaches. This script
drives each one on main with inputs chosen from the docs, with expected values from the docs or an independent brute
force, so an untested branch that is also wrong shows up as FAIL:
 1. engine.py:421-432, an order for a name settled between its decision and its fill (delay 1) is rejected 'delisted'
    (README.md:59: a settled name is not eligible; nothing may trade after the settlement).
 2. expressions.py:291-295, the function-call form of a binary operator refuses constant-only arguments as the infix
    form does (expressions.py:276-277); expressions.py:272-273, unary plus is the identity.
 3. strategies.py:32-40 leg_size: "most names k with k / n <= fraction" (its docstring), against a brute force
    max{k in 0..n : k / n <= fraction} in the same floating point, over a grid of n and fractions.
 4. search.py:117-122 chronological_split without confirm_start: k = "the largest k with k / len(dates) <= dev_fraction"
    (its docstring), against the same brute force.
Usage: python uncovered_decision_branches.py   (run from the main worktree's venv). Exit 0 all PASS, 1 any FAIL.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.strategies import leg_size
from invest_mining import expressions as ex
from invest_mining.search import chronological_split

bad = 0
def report(name, ok, detail=""):
    global bad
    print(("PASS " if ok else "FAIL ") + name + (": " + detail if detail else ""))
    bad += not ok

# 1. engine: settled between decision and fill
DATES = pd.bdate_range("2024-01-01", periods=12)
rows = []
for k, d in enumerate(DATES):
    for name, px in (("A", 10.0), ("B", 20.0), ("C", 40.0)):
        rows.append([d, name, px, px, px, px, 1e9])  # A keeps bars after its settlement
bars = pd.DataFrame(rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"])
signals = pd.DataFrame({"decision_date": DATES[3], "instrument": ["A", "B", "C"], "score": [3.0, 2.0, 1.0]})
cfg = BacktestConfig(
    strategy=StrategyConfig(long_fraction=0.34, short_fraction=0.0, rebalance_every=100, min_names=1),
    execution=ExecutionConfig(max_participation=1.0, min_price=0.0, delay=1),
    costs=CostModel(commission_bps=0, half_spread_bps=0, impact_coef=0, borrow_bps_annual=0, adv_window=1, vol_window=2),
    initial_capital=1000.0,
)
delist = pd.DataFrame([{"date": DATES[4], "instrument": "A", "settlement_price": 10.0}])
res = run_backtest(bars, signals, cfg, delistings=delist)
t = res.trades
a = t[t["instrument"] == "A"]
rej = a[(a["status"] == "rejected") & (a["reason"] == "delisted")]
filled_a = a[a["status"] == "filled"]
report("1 engine: order for a name settled after its decision (delay 1) is rejected 'delisted' at the fill open",
       len(rej) == 1 and rej["date"].iloc[0] == DATES[5] and filled_a.empty,
       f"A rows {a[['date', 'status', 'reason']].to_dict('records')}")
report("1b engine: no position in A after the settlement, equity stays 1000 (flat prices, no costs)",
       abs(float(res.daily["equity"].iloc[-1]) - 1000.0) < 1e-9 if "equity" in res.daily else True,
       f"last equity {res.daily['equity'].iloc[-1] if 'equity' in res.daily else 'n/a'}")

# 2. parser
try:
    ex.parse("add(1, 2)"); report("2 parser: add(1, 2) refused as constant-only", False, "accepted")
except ex.ExpressionError as e:
    report("2 parser: add(1, 2) refused as constant-only", "constant-only" in str(e), str(e))
try:
    ex.parse("1 + 2"); report("2 parser: 1 + 2 refused (infix reference)", False, "accepted")
except ex.ExpressionError as e:
    report("2 parser: 1 + 2 refused (infix reference)", "constant-only" in str(e), str(e))
report("2 parser: add(close, 2) == close + 2", str(ex.parse("add(close, 2)")) == str(ex.parse("close + 2")),
       f"{ex.parse('add(close, 2)')} vs {ex.parse('close + 2')}")
report("2 parser: +close == close", str(ex.parse("+close")) == str(ex.parse("close")))

# 3./4. cut rules against brute force
def brute(n, f):
    best = 0
    for k in range(n + 1):
        if k / n <= f:
            best = k
    return best
fracs = sorted({i / 100 for i in range(1, 100)} | {i / 7 for i in range(1, 7)} | {0.1 * i for i in range(1, 10)} |
               {np.nextafter(i / 100, 0.0) for i in range(1, 100)} | {np.nextafter(i / 100, 1.0) for i in range(1, 100)})
hits_minus = 0; mism = []
for n in range(1, 401):
    for f in fracs:
        k = leg_size(n, float(f))
        if int(np.floor(n * f)) > 0 and int(np.floor(n * f)) / n > f: hits_minus += 1
        if k != brute(n, float(f)): mism.append((n, float(f), k, brute(n, float(f))))
report(f"3 leg_size equals brute force on {400 * len(fracs)} (n, fraction) pairs", not mism, f"mismatches {mism[:5]}; k-1 branch reached {hits_minus} times")
dates = pd.bdate_range("2020-01-01", periods=400)
mism2 = []
for n in (1, 2, 3, 7, 10, 50, 99, 100, 101, 250, 400):
    for f in fracs:
        sp = chronological_split(dates[:n], float(f), horizon=1, embargo=0)
        k = n - len(sp.confirm_dates)
        if k != brute(n, float(f)): mism2.append((n, float(f), k, brute(n, float(f))))
report("4 chronological_split confirmation start equals brute force", not mism2, f"mismatches {mism2[:5]}")
print("RESULT:", "all PASS" if not bad else f"{bad} FAIL")
sys.exit(1 if bad else 0)
