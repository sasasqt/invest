"""Open place 2026-11-15 (execution.delay = 1 variant of RA-2026-11-15-1).
RA-2026-11-15-1 (repo audit 2026-11-15; found by reviewer 2, verified by the run).

The engine fills an entry on a session whose traded volume is 0 (bars present, a trading
halt or an illiquid stretch) because eligibility and the participation cap use the trailing
ADV (engine.py:214-217 rolling mean with min_periods=adv_window; :533-538 `ADV > min_adv_dollar`),
which stays positive until the whole window is zero. Nothing traded on that session, so no
order could have filled there; the participation reported (against trailing ADV) hides it.
Sibling of REVIEW-27 / BF-2026-10-26-1 (exits that cannot trade), here on the entry side.

Expected (physical, independent of the engine): no fill on an instrument-session whose volume is 0.
usage: python -I ra_fill_on_zero_volume_session.py   (exit 1 = the defect is present)"""
import sys
import numpy as np
import pandas as pd
from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import run_backtest


class HoldXFrom:
    """Long Y until decision index `switch`, then long X (an entry of X inside the stretch)."""
    def __init__(self, switch: int) -> None:
        self.switch, self.i = switch, 0
    def target_weights(self, scores: pd.Series) -> pd.Series:
        w = pd.Series(0.0, index=scores.dropna().index)  # eligible names only
        want = "X" if self.i >= self.switch else "Y"
        self.i += 1
        if want not in w.index:                           # X drops out once its whole ADV window is 0
            want = "Y"
        if want in w.index:                               # nothing is eligible before the windows fill
            w[want] = 1.0
        return w


dates = pd.bdate_range("2024-01-01", periods=100)
H0, H1 = 40, 70                     # X trades 0 shares on sessions [H0, H1); bars present, price flat
rng = np.random.default_rng(1)
pxX = 10 * np.cumprod(1 + rng.normal(0, 0.01, len(dates)))
pxY = 20 * np.cumprod(1 + rng.normal(0, 0.01, len(dates)))
rows = []
for k, d in enumerate(dates):
    halted = H0 <= k < H1
    px = pxX[H0 - 1] if halted else pxX[k]
    rows.append([d, "X", px, px, px, px, 0.0 if halted else 1e6])
    rows.append([d, "Y", pxY[k], pxY[k], pxY[k], pxY[k], 1e6])
bars = pd.DataFrame(rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"])
sig = pd.DataFrame([[d, n, 1.0] for d in dates for n in ("X", "Y")], columns=["decision_date", "instrument", "score"])
cfg = BacktestConfig(
    strategy=StrategyConfig(long_fraction=0.5, short_fraction=0.0, gross_leverage=1.0, min_names=1, rebalance_every=1),
    execution=ExecutionConfig(max_participation=0.05, min_price=0.0, min_adv_dollar=0.0, delay=1),
    costs=CostModel(commission_bps=0, half_spread_bps=0, impact_coef=0.1, borrow_bps_annual=0, adv_window=20, vol_window=20),
    initial_capital=1e5,
)
# the strategy is called once per session from session 0 (rebalance_every=1); a decision on session k
# fills on k+1, so switching at call H0+9 asks for X on session H0+10, ten sessions into the stretch
res = run_backtest(bars, sig, cfg, HoldXFrom(switch=H0 + 9))
t = res.trades.copy()
k_of = {d: k for k, d in enumerate(dates)}
t["k"] = t["date"].map(k_of)
vol = bars.set_index(["date", "instrument"])["volume"]
t["session_volume"] = [vol.get((d, n), np.nan) for d, n in zip(t["date"], t["instrument"])]
bad = t[(t["status"] == "filled") & (t["session_volume"] == 0)]
print(f"trades {len(t)}; X rows on zero-volume sessions {int(((t['instrument'] == 'X') & (t['session_volume'] == 0)).sum())}")
cols = ["date", "k", "instrument", "status", "shares", "notional", "participation", "session_volume"]
if len(bad):
    print("FILLED on a session with volume 0:\n" + bad[cols].to_string(index=False))
    print(f"FAIL: {len(bad)} fill(s) on zero-volume sessions; largest notional {bad['notional'].abs().max():.2f}, "
          f"reported participation {bad['participation'].max():.4f} (of trailing ADV)")
    sys.exit(1)
print("PASS: no fill on a zero-volume session")
