"""Accounting lens (first use this run): identities between eval/tables/daily.csv, trades.csv, eval/config.json and metrics.json.

Formulas written from the engine docstring (event order), METRICS.md and the config, not from the code: per session
equity = cash + long - short; cash moves by -(filled notionals) - trading costs - borrow + financing; the day's costs equal the
filled trades' costs; cum_costs is their running sum; turnover = traded notional / previous equity; commission and spread equal
traded notional times their bps; return and gross return follow from equity and the day's costs; participation never exceeds
max_participation; total_return in metrics.json equals equity_end / initial - 1.
Usage: python lens_accounting.py <eval dir>. Exit 0 when every identity holds (|diff| <= 1e-6 relative), 1 otherwise.
"""
import json, sys
import numpy as np, pandas as pd
d = sys.argv[1]
daily = pd.read_csv(f"{d}/tables/daily.csv", parse_dates=["date"])
trades = pd.read_csv(f"{d}/tables/trades.csv", parse_dates=["date"])
cfg = json.load(open(f"{d}/config.json", encoding="utf-8")); metrics = json.load(open(f"{d}/metrics.json", encoding="utf-8"))
cm, ex = cfg["costs"], cfg["execution"]; init = cfg["initial_capital"]
bad = []
def check(name, lhs, rhs, tol=1e-6):
    lhs, rhs = np.asarray(lhs, dtype=float), np.asarray(rhs, dtype=float)
    scale = np.maximum(1.0, np.abs(rhs)); worst = float(np.nanmax(np.abs(lhs - rhs) / scale)) if len(lhs) else 0.0
    ok = worst <= tol
    print(f"{'ok  ' if ok else 'FAIL'} {name}: worst relative diff {worst:.3e} over {len(lhs)} rows")
    if not ok: bad.append(name)
filled = trades[trades["status"] == "filled"]
by_day = filled.groupby("date").agg(notional=("notional", "sum"), abs_notional=("notional", lambda s: s.abs().sum()),
                                     commission=("commission", "sum"), spread=("spread", "sum"), impact=("impact", "sum"))
by_day = by_day.reindex(daily["date"]).fillna(0.0)
liq = filled[filled["reason"] == "delisted_liquidation"].groupby("date")["notional"].apply(lambda s: s.abs().sum()).reindex(daily["date"]).fillna(0.0)
prev_equity = daily["equity"].shift(1).fillna(init); prev_cash = daily["cash"].shift(1).fillna(init)
costs = daily[["commission_cost", "spread_cost", "impact_cost"]].sum(axis=1)
check("equity = cash + long_value - short_value", daily["equity"], daily["cash"] + daily["long_value"] - daily["short_value"])
check("commission_cost = sum of filled trades' commission", daily["commission_cost"], by_day["commission"].to_numpy())
check("spread_cost = sum of filled trades' spread", daily["spread_cost"], by_day["spread"].to_numpy())
check("impact_cost = sum of filled trades' impact", daily["impact_cost"], by_day["impact"].to_numpy())
check("traded_notional = sum |notional| of filled trades (settlements excluded)", daily["traded_notional"], (by_day["abs_notional"] - liq).to_numpy())
check("cash_t - cash_t-1 = -filled notional - trading costs - borrow + financing", daily["cash"] - prev_cash,
      -by_day["notional"].to_numpy() - costs - daily["borrow_cost"] + daily["financing"])
check("cum_costs = running sum of commission+spread+impact+borrow", daily["cum_costs"], (costs + daily["borrow_cost"]).cumsum())
check("turnover = traded_notional / previous equity", daily["turnover"], daily["traded_notional"] / prev_equity)
check("commission_cost = traded_notional * commission_bps/1e4 (fills only)", daily["commission_cost"], daily["traded_notional"] * cm["commission_bps"] / 1e4)
check("spread_cost = traded_notional * half_spread_bps/1e4", daily["spread_cost"], daily["traded_notional"] * cm["half_spread_bps"] / 1e4)
check("return = equity/prev - 1", daily["return"], daily["equity"] / prev_equity - 1)
check("gross_return = (equity + day costs incl. borrow)/prev - 1", daily["gross_return"], (daily["equity"] + costs + daily["borrow_cost"]) / prev_equity - 1)
check("equity_before_costs = initial * cumprod(1 + gross_return)", daily["equity_before_costs"], init * (1 + daily["gross_return"]).cumprod())
check("gross_exposure = (long+short)/equity", daily["gross_exposure"], (daily["long_value"] + daily["short_value"]) / daily["equity"])
check("net_exposure = (long-short)/equity", daily["net_exposure"], (daily["long_value"] - daily["short_value"]) / daily["equity"])
check("metrics total_return = equity_end/initial - 1", [metrics["performance"]["total_return"]["value"]], [daily["equity"].iloc[-1] / init - 1])
part = filled["participation"].dropna()
over = part[part > ex["max_participation"] * (1 + 1e-9)]
print(f"{'ok  ' if over.empty else 'FAIL'} participation <= max_participation {ex['max_participation']}: {len(over)} of {len(part)} filled trades exceed it (max {part.max():.6f})")
if not over.empty: bad.append("participation cap")
fill_days = daily[daily["traded_notional"] > 0]
gross_after = (fill_days["long_value"] + fill_days["short_value"]) / fill_days["equity"]
lev = cfg["strategy"]["gross_leverage"]
print(f"info gross exposure on {len(fill_days)} fill days: median {gross_after.median():.4f}, min {gross_after.min():.4f}, max {gross_after.max():.4f} vs gross_leverage {lev} (caps, rejections and intraday moves make it differ; not a pass/fail)")
print(f"info rejected trades {int((trades['status'] == 'rejected').sum())}, clipped {int((filled['reason'] == 'participation_cap').sum())}, settlements {int((filled['reason'] == 'delisted_liquidation').sum())}; borrow days {int((daily['borrow_cost'] > 0).sum())}; financing nonzero days {int((daily['financing'] != 0).sum())}")
print("RESULT:", "all identities hold" if not bad else f"{len(bad)} identities fail: {bad}")
sys.exit(1 if bad else 0)
