"""Statistics lens: recompute headline metrics from eval/tables/daily.csv with numpy and the standard library, from the
formulas in strategy-evaluation/METRICS.md sections 3 to 6 (written from the document, not from metrics.py), and compare with
eval/metrics.json. Conventions taken from the document: sample standard deviation (ddof 1); CAGR with elapsed years =
periods / annualization (the metric's own `day_count` note); r_t = V_t / V_{t-1} - 1 with V_0 = initial capital; drawdown
D_t = V_t / max(V_0..V_t) - 1; downside deviation over all periods with MAR per period; Sortino = mean(r - m) * A / (dd * sqrt(A)).
Usage: python recompute_metrics.py <eval dir>   Exit 0 when every recomputed value agrees within 1e-9 relative (1e-12 absolute), 1 otherwise."""
import csv, json, math, statistics, sys
import numpy as np
d = sys.argv[1]
cfg = json.load(open(f"{d}/config.json")); m = json.load(open(f"{d}/metrics.json"))
A = cfg["annualization"]; V0 = cfg["initial_capital"]; rf = cfg["risk_free_annual"]; mar = cfg["mar_annual"]
rows = list(csv.DictReader(open(f"{d}/tables/daily.csv")))
V = np.array([float(r["equity"]) for r in rows]); N = len(V)
r = V / np.concatenate(([V0], V[:-1])) - 1.0
r_file = np.array([float(x["return"]) for x in rows])
rf_p = (1 + rf) ** (1 / A) - 1; m_p = (1 + mar) ** (1 / A) - 1
out = {}
out["total_return"] = V[-1] / V0 - 1
out["net_profit"] = V[-1] - V0
out["mean_return"] = r.mean(); out["median_return"] = float(np.median(r))
out["geometric_mean_return"] = (V[-1] / V0) ** (1 / N) - 1
out["variance_return"] = r.var(ddof=1)
out["annual_arithmetic_mean"] = A * r.mean()
out["cagr"] = (V[-1] / V0) ** (A / N) - 1
out["annual_volatility"] = r.std(ddof=1) * math.sqrt(A)
dd_dev = math.sqrt(np.mean(np.minimum(r - m_p, 0.0) ** 2))
out["downside_deviation"] = dd_dev; out["annual_downside_volatility"] = dd_dev * math.sqrt(A)
e = r - rf_p
out["sharpe"] = e.mean() / e.std(ddof=1) * math.sqrt(A)
out["sortino"] = (r - m_p).mean() * A / (dd_dev * math.sqrt(A))
peak = np.maximum.accumulate(np.concatenate(([V0], V)))[1:]
D = V / peak - 1.0
out["max_drawdown"] = -D.min(); out["current_drawdown"] = -D[-1]
out["ulcer_index"] = math.sqrt(np.mean(D ** 2))
out["average_drawdown"] = float(np.mean(-D))
out["time_under_water"] = float(np.mean(D < 0))
out["calmar"] = out["cagr"] / out["max_drawdown"]
out["omega"] = np.maximum(r - m_p, 0).sum() / np.maximum(m_p - r, 0).sum()
out["gain_to_pain"] = r.sum() / abs(r[r < 0].sum())
out["hit_rate"] = float(np.mean(r > 0))
out["best_period"] = r.max(); out["worst_period"] = r.min()
out["martin"] = ((r - m_p).mean() * A) / out["ulcer_index"]
L = -r; out["var_loss_95"] = float(np.quantile(L, 0.95)); out["expected_shortfall_95"] = float(L[L >= np.quantile(L, 0.95)].mean())
out["tail_ratio"] = float(np.quantile(r, 0.95) / abs(np.quantile(r, 0.05)))
# drawdown duration (peak to recovery, sessions; the open episode is censored)
mdd_i = int(np.argmin(D)); peak_i = int(np.argmax(V[:mdd_i + 1] >= peak[mdd_i]))  # first index reaching that peak
rec = next((i for i in range(mdd_i, N) if V[i] >= peak[mdd_i]), None)
out["max_drawdown_duration"] = (rec if rec is not None else N - 1) - peak_i
bad = 0
print(f"{'metric':28} {'recomputed':>22} {'metrics.json':>22} status")
for k, v in out.items():
    mj = m["performance"].get(k, {}); ref = mj.get("value")
    if ref is None:
        print(f"{k:28} {v:22.10g} {'n/a':>22} ({mj.get('reason')})"); continue
    ok = math.isclose(v, ref, rel_tol=1e-9, abs_tol=1e-12)
    loose = math.isclose(v, ref, rel_tol=1e-3, abs_tol=1e-6)
    tag = "agree" if ok else ("within 0.1 % (convention)" if loose else "DIFFERS")
    bad += not loose
    print(f"{k:28} {v:22.10g} {ref:22.10g} {tag}")
print("daily.csv 'return' column equals V_t/V_{t-1}-1:", bool(np.allclose(r, r_file, rtol=0, atol=1e-12)))
print("periods:", N, "metrics.json periods:", m["performance"]["periods"]["value"], "censored flag:", (m["performance"]["max_drawdown_duration"].get("extra") or {}).get("censored"))
sys.exit(1 if bad else 0)
