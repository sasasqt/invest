"""Check: when `end` lies before the first signal session, invest-eval's refusal should name the cause (no
signal session on or before `end`), not "evaluation window has fewer than two sessions" (the window from the
default start = first signal session to `end` is empty, but the calendar before `end` has many sessions).
Usage: ra_empty_window_message.py <main worktree> <synthetic workflow out dir>; exit 1 on main (message misleading)."""
import json, pathlib, subprocess, sys, tempfile
import pandas as pd
from invest_data.schemas import read_market_bars, read_signals
wt, synth = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
_, bars = read_market_bars(synth / "data/market"); _, sig = read_signals(synth / "signals")
cal = pd.DatetimeIndex(sorted(pd.to_datetime(bars["date"]).unique())); first = pd.Timestamp(sig["decision_date"].min())
i = cal.get_loc(first); end = cal[i - 5]; n_before = int((cal <= end).sum())
cfg = json.loads((wt / "strategy-evaluation/examples/quantile_long_short.json").read_text(encoding="utf-8")); cfg["end"] = end.strftime("%Y-%m-%d")
with tempfile.TemporaryDirectory() as td:
    cfgp = pathlib.Path(td) / "cfg.json"; cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([str(wt / ".venv/bin/invest-eval"), "run", "--data", str(synth / "data/market"), "--universe", str(synth / "data/universe"), "--signals", str(synth / "signals"), "--config", str(cfgp), "--out", str(pathlib.Path(td) / "out")], capture_output=True, text=True)
msg = (r.stderr + r.stdout).strip().splitlines()[-1] if (r.stderr + r.stdout).strip() else ""
print(f"end={end.date()} first signal={first.date()} sessions on or before end={n_before} rc={r.returncode}\nmessage: {msg}")
ok = r.returncode != 0 and "signal" in msg.lower()
print("RESULT:", "PASS (refusal names the missing signals)" if ok else "FAIL (refusal does not name the cause: the calendar has sessions before end; none carries a signal)")
sys.exit(0 if ok else 1)
