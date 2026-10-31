"""OP-2026-10-31-4 probe: does cfg.start set before the first signal dilute the strategy's and the
benchmark's statistics, and does any doc warn? Usage (with the worktree's venv python):
  python -I op4_start_dilution.py <main worktree> <synthetic workflow out dir> <probe out dir>
Runs invest-eval twice on the same synthetic market/universe/signals with validation.benchmark = "universe":
(a) start = null (default: first signal session) and (b) start = 60 sessions before the first signal.
Prints sessions, Sharpe, IR, CAGR, volatility and benchmark total return for both; exit 0 always (a probe)."""
import json, pathlib, shutil, subprocess, sys
import pandas as pd
from invest_data.schemas import read_market_bars, read_signals

wt, synth, out = (pathlib.Path(a) for a in sys.argv[1:4])
_, bars = read_market_bars(synth / "data/market")
_, sig = read_signals(synth / "signals")
cal = pd.DatetimeIndex(sorted(pd.to_datetime(bars["date"]).unique()))
first = pd.Timestamp(sig["decision_date"].min())
i = cal.get_loc(first)
start60 = cal[max(i - 60, 0)]
cfg = json.loads((wt / "strategy-evaluation/examples/quantile_long_short.json").read_text(encoding="utf-8"))
cfg["validation"]["benchmark"] = "universe"
out.mkdir(parents=True, exist_ok=True)
rows = {}
for name, start in (("default", None), ("start_minus_60", start60.strftime("%Y-%m-%d"))):
    c = json.loads(json.dumps(cfg)); c["start"] = start
    cfgp = out / f"cfg_{name}.json"; cfgp.write_text(json.dumps(c, indent=1), encoding="utf-8")
    od = out / name; shutil.rmtree(od, ignore_errors=True)
    r = subprocess.run([str(wt / ".venv/bin/invest-eval"), "run", "--data", str(synth / "data/market"), "--universe", str(synth / "data/universe"), "--signals", str(synth / "signals"), "--config", str(cfgp), "--out", str(od)], capture_output=True, text=True)
    if r.returncode != 0:
        print(name, "invest-eval rc", r.returncode, r.stderr[-800:]); continue
    m = json.loads((od / "metrics.json").read_text(encoding="utf-8")); v = json.loads((od / "verdict.json").read_text(encoding="utf-8"))
    d = pd.read_csv(od / "tables/daily.csv")
    flat = int((d.get("gross_exposure", pd.Series([1.0] * len(d))) == 0).sum()) if "gross_exposure" in d else None
    def g(sec, k):
        x = m.get(sec, {}).get(k, {}); return (x.get("value"), x.get("status")) if isinstance(x, dict) else x
    rows[name] = {"start": start, "sessions": len(d), "first_daily_date": str(d["date"].iloc[0]), "flat_sessions(gross_exposure==0)": flat,
                  "sharpe": g("performance", "sharpe"), "cagr": g("performance", "cagr"), "annual_volatility": g("performance", "annual_volatility"),
                  "benchmark_total_return": g("benchmark", "benchmark_total_return"), "information_ratio": g("benchmark", "information_ratio"), "alpha_annual": g("benchmark", "alpha_annual"),
                  "evaluation_window": v.get("portfolio", {}).get("evaluation_window"), "portfolio_status": v.get("portfolio", {}).get("status")}
print("first signal session:", first.date(), "| 60 sessions earlier:", start60.date(), "| calendar", cal[0].date(), "..", cal[-1].date(), f"({len(cal)} sessions)")
print(json.dumps(rows, indent=1, default=str))
