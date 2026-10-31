#!/usr/bin/env python3
"""Evaluation lens (repo audit 2026-10-31): accounting identities, statistics recomputation, reported outputs, timing.

Usage: python3 -I lens_eval.py <workflow out dir>   (needs <dir>/eval; uses data/market, signals, mining when present)

Formulas are written from strategy-evaluation/METRICS.md (sections 1, 4, 5, 6, 7, 8), Bailey & Lopez de Prado
(PSR, DSR) and Newey & West (1987) with Bartlett weights, in numpy and statistics.NormalDist. Nothing is imported
from invest_evaluation. Where METRICS.md leaves a convention open (day count for CAGR, quantile method for VaR,
population or sample moments) the documented alternatives are tried and the matching one is named.
Lines: PASS|FAIL|INFO <id>: <detail>. FAIL = no documented convention reproduces the reported value. Exit 1 on FAIL.
"""
from __future__ import annotations
import json, math, re, sys
from pathlib import Path
from statistics import NormalDist
import numpy as np, pandas as pd

ND = NormalDist(); EG = 0.5772156649015329; fails = 0

def out(st, name, detail=""):
    global fails
    if st == "FAIL": fails += 1
    print(f"{st} {name}: {detail}")

def close(a, b, rel=1e-9, ab=1e-9):
    if a is None or b is None: return a is None and b is None
    try: a = float(a); b = float(b)
    except (TypeError, ValueError): return a == b
    if math.isnan(a) and math.isnan(b): return True
    return abs(a - b) <= ab + rel * max(abs(a), abs(b))

def cmp(name, reported, cands, rel=1e-9, ab=1e-9):
    for lab, v in cands.items():
        if close(reported, v, rel, ab):
            out("PASS", name, f"{reported!r} == {lab} {v!r}"); return lab
    out("FAIL", name, f"reported {reported!r}; candidates " + ", ".join(f"{k}={v!r}" for k, v in cands.items()))
    return None

def val(m, g, k):
    x = m.get(g, {}).get(k); return None if x is None else x.get("value")

def hac(x, lags=None):
    x = np.asarray(x, float); n = len(x)
    if lags is None: lags = math.floor(4 * (n / 100) ** (2 / 9))
    e = x - x.mean(); lr = float(e @ e) / n
    for l in range(1, min(lags, n - 1) + 1): lr += 2 * (1 - l / (lags + 1)) * float(e[l:] @ e[:-l]) / n
    se = math.sqrt(lr / n); return {"lags": lags, "se": se, "t": float(x.mean() / se), "n": n}

def psr(x, sr0):
    x = np.asarray(x, float); n = len(x); sr = x.mean() / x.std(ddof=1); mm = x - x.mean(); s2 = np.mean(mm ** 2)
    sk = float(np.mean(mm ** 3) / s2 ** 1.5); ku = float(np.mean(mm ** 4) / s2 ** 2)
    den = 1 - sk * sr + (ku - 1) / 4 * sr ** 2
    return {"sr": float(sr), "skew": sk, "kurt": ku, "p": ND.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(den))}

def dd_stats(V):
    P = np.maximum.accumulate(V); D = V / P - 1; D1 = D[1:]
    under = D1 < 0; episodes = []; i = 0
    while i < len(D1):
        if under[i]:
            j = i
            while j < len(D1) and under[j]: j += 1
            trough = i + int(np.argmin(D1[i:j])); episodes.append((i, j, trough, j < len(D1))); i = j
        else: i += 1
    return D, D1, episodes

def main(root):
    root = Path(root); E = root / "eval"
    cfg = json.loads((E / "config.json").read_text()); M = json.loads((E / "metrics.json").read_text())
    S = json.loads((E / "statistics.json").read_text()); VD = json.loads((E / "verdict.json").read_text())
    d = pd.read_csv(E / "tables/daily.csv", dtype={"date": str}); tr = pd.read_csv(E / "tables/trades.csv", dtype={"date": str, "decision_date": str})
    ep = pd.read_csv(E / "tables/episodes.csv", dtype={"entry_date": str, "exit_date": str}); sc = pd.read_csv(E / "tables/scenarios.csv")
    A = cfg["annualization"]; rf = cfg["risk_free_annual"]; mar = cfg["mar_annual"]; V0 = cfg["initial_capital"]; ex = cfg["execution"]; co = cfg["costs"]
    n = len(d); eq = d.equity.to_numpy(float); prev = np.concatenate([[V0], eq[:-1]]); r = d["return"].to_numpy(float); g = d.gross_return.to_numpy(float)
    costs = d[["commission_cost", "spread_cost", "impact_cost", "borrow_cost", "financing"]].sum(axis=1).to_numpy(float)
    print(f"== {root} ({n} sessions {d.date.iloc[0]}..{d.date.iloc[-1]}, A={A}, rf={rf}, mar={mar}, V0={V0}, delay={ex['delay']})")
    # ---- accounting
    out("PASS" if np.allclose(eq, prev * (1 + r), rtol=1e-9, atol=1e-6) else "FAIL", "A1 equity_t = equity_t-1 (1+return_t)", f"max abs dev {np.max(np.abs(eq - prev*(1+r))):.3g}")
    ebc = d.equity_before_costs.to_numpy(float); prev_ebc = np.concatenate([[V0], ebc[:-1]])
    out("PASS" if np.allclose(ebc, eq + d.cum_costs.to_numpy(float), rtol=1e-9, atol=1e-6) else "INFO", "A2a equity_before_costs = equity + cum_costs", f"max abs dev {np.max(np.abs(ebc - eq - d.cum_costs.to_numpy(float))):.3g}")
    out("PASS" if np.allclose(ebc, prev_ebc * (1 + g), rtol=1e-9, atol=1e-6) else "INFO", "A2b equity_before_costs_t = ebc_t-1 (1+gross_return_t)", f"max abs dev {np.max(np.abs(ebc - prev_ebc*(1+g))):.3g}")
    out("PASS" if np.allclose(d.cum_costs.to_numpy(float), np.cumsum(costs), rtol=1e-9, atol=1e-6) else "FAIL", "A3 cum_costs = cumsum(commission+spread+impact+borrow+financing)", f"max abs dev {np.max(np.abs(d.cum_costs.to_numpy(float) - np.cumsum(costs))):.3g}")
    L = d.long_value.to_numpy(float); Sh = d.short_value.to_numpy(float); cash = d.cash.to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        gx = (L + np.abs(Sh)) / eq; nx = (L - np.abs(Sh)) / eq
    out("PASS" if np.allclose(gx, d.gross_exposure, rtol=1e-9, atol=1e-12) and np.allclose(nx, d.net_exposure, rtol=1e-9, atol=1e-12) else "FAIL", "A4 gross = (long+|short|)/equity, net = (long-|short|)/equity", f"short_value sign: min {Sh.min():.3g} max {Sh.max():.3g}; max dev gross {np.max(np.abs(gx - d.gross_exposure)):.3g} net {np.max(np.abs(nx - d.net_exposure)):.3g}")
    out("PASS" if np.allclose(cash + L - np.abs(Sh), eq, rtol=1e-9, atol=1e-6) else "FAIL", "A5 cash + long - |short| = equity", f"max abs dev {np.max(np.abs(cash + L - np.abs(Sh) - eq)):.3g}")
    tn = d.traded_notional.to_numpy(float)
    cmp("A6 turnover_t", float(np.max(np.abs(d.turnover.to_numpy(float) - tn / prev))), {"max|turnover - traded_notional/equity_t-1| (0 expected)": 0.0}, ab=1e-9)
    out("INFO", "A7 gross return definition", f"(gross_return - return)*equity_t-1 vs session costs: max abs dev {np.max(np.abs((g - r)*prev - costs)):.3g} (0 only if gross = net + costs/equity_t-1; the tables define gross through equity_before_costs = equity + cum_costs, see A2a/A2b)")
    st = tr.status.value_counts().to_dict(); out("INFO", "A8 trade statuses", str(st))
    f = tr[tr.status == "filled"]
    out("PASS" if np.allclose(f.notional, f.shares * f.price, rtol=1e-9, atol=1e-6) else "FAIL", "A8a notional = shares x price", f"{len(f)} fills")
    out("PASS" if np.allclose(f.commission, f.notional.abs() * co["commission_bps"] / 1e4, rtol=1e-9, atol=1e-6) and np.allclose(f.spread, f.notional.abs() * co["half_spread_bps"] / 1e4, rtol=1e-9, atol=1e-6) else "FAIL", "A8b commission = |notional| bps/1e4, spread = |notional| half_spread_bps/1e4", f"commission_bps {co['commission_bps']} half_spread_bps {co['half_spread_bps']}")
    agg = f.groupby("date").agg(tn=("notional", lambda s: s.abs().sum()), com=("commission", "sum"), spr=("spread", "sum"), imp=("impact", "sum"), k=("notional", "size")).reindex(d.date).fillna(0.0)
    out("PASS" if np.allclose(agg.tn, tn, rtol=1e-9, atol=1e-6) and np.allclose(agg.com, d.commission_cost, rtol=1e-9, atol=1e-6) and np.allclose(agg.spr, d.spread_cost, rtol=1e-9, atol=1e-6) and np.allclose(agg.imp, d.impact_cost, rtol=1e-9, atol=1e-6) else "FAIL", "A8c daily traded_notional/commission/spread/impact = sums over that day's fills", f"max dev tn {np.max(np.abs(agg.tn - tn)):.3g} com {np.max(np.abs(agg.com - d.commission_cost)):.3g} spr {np.max(np.abs(agg.spr - d.spread_cost)):.3g} imp {np.max(np.abs(agg.imp - d.impact_cost)):.3g}")
    rej = tr[tr.status != "filled"].groupby("date").size().reindex(d.date).fillna(0)
    capped = f[np.isclose(f.participation, ex["max_participation"], rtol=1e-9, atol=1e-12)].groupby("date").size().reindex(d.date).fillna(0)
    out("PASS" if (rej.to_numpy() == d.n_rejected.to_numpy()).all() else "INFO", "A8d n_rejected = non-filled trade rows per day", f"sum rows {int(rej.sum())} vs sum n_rejected {int(d.n_rejected.sum())}")
    out("PASS" if (capped.to_numpy() == d.n_clipped.to_numpy()).all() else "INFO", "A8e n_clipped = fills at participation == max_participation", f"sum {int(capped.sum())} vs n_clipped {int(d.n_clipped.sum())}")
    T = lambda k: val(M, "trading", k)
    for k, v in {"total_commission_cost": d.commission_cost.sum(), "total_spread_cost": d.spread_cost.sum(), "total_impact_cost": d.impact_cost.sum(), "total_borrow_cost": d.borrow_cost.sum(), "total_financing": d.financing.sum(), "total_costs": costs.sum(), "fills": len(f), "rejected_orders": int(d.n_rejected.sum()), "participation_capped_fills": int(d.n_clipped.sum()), "average_gross_exposure": float(d.gross_exposure.mean()), "max_gross_exposure": float(d.gross_exposure.max()), "average_net_exposure": float(d.net_exposure.mean()), "average_positions": float((d.n_long + d.n_short).mean()), "max_participation": float(f.participation.max()) if len(f) else None}.items():
        if k in M.get("trading", {}): cmp(f"A9 trading.{k}", T(k), {"recomputed": v}, rel=1e-9, ab=1e-6)
    years = n / A
    if "turnover_one_way_annual" in M["trading"]: cmp("A9 trading.turnover_one_way_annual", T("turnover_one_way_annual"), {"sum(turnover)/2/years": d.turnover.sum() / 2 / years, "sum(turnover)/years": d.turnover.sum() / years, "sum(|dw|)/2 per rebalance *A/n (n/a here)": float("nan")})
    # statistics
    P = lambda k: val(M, "performance", k)
    cmp("S periods", P("periods"), {"n": n})
    cmp("S total_return", P("total_return"), {"V_end/V_0-1": eq[-1] / V0 - 1}); cmp("S net_profit", P("net_profit"), {"V_end-V_0": eq[-1] - V0}, ab=1e-6)
    days = (pd.Timestamp(d.date.iloc[-1]) - pd.Timestamp(d.date.iloc[0])).days
    Ycands = {"n/A": n / A, "calendar days/365.25": days / 365.25, "(n-1)/A": (n - 1) / A, "(calendar days+1)/365.25": (days + 1) / 365.25}
    ylab = cmp("S cagr", P("cagr"), {f"(V_end/V_0)^(1/Y)-1, Y={k}": (eq[-1] / V0) ** (1 / y) - 1 for k, y in Ycands.items()})
    Y = Ycands[ylab.split("Y=")[1]] if ylab else n / A
    if "cost_drag_annual" in M["trading"]:
        Vg = V0 * np.cumprod(1 + g); gc = (Vg[-1] / V0) ** (1 / Y) - 1
        cmp("A9 trading.cost_drag_annual", T("cost_drag_annual"), {"gross cagr - net cagr": gc - P("cagr"), "sum(costs)/V0 * A/n": costs.sum() / V0 * A / n, "mean(costs/equity_t-1)*A": float(np.mean(costs / prev)) * A, "sum(costs)/mean(equity)/years": costs.sum() / eq.mean() / years, "(mean(g)-mean(r))*A": float((g - r).mean()) * A, "gross annual_arithmetic_mean - net": (g.mean() - r.mean()) * A, "mean(costs/ebc_t-1)*A": float(np.mean(costs / prev_ebc)) * A})
    cmp("S mean_return", P("mean_return"), {"mean": r.mean()}); cmp("S median_return", P("median_return"), {"median": float(np.median(r))})
    cmp("S geometric_mean_return", P("geometric_mean_return"), {"(V_end/V_0)^(1/n)-1": (eq[-1] / V0) ** (1 / n) - 1})
    cmp("S annual_arithmetic_mean", P("annual_arithmetic_mean"), {"mean*A": r.mean() * A})
    cmp("S variance_return", P("variance_return"), {"var ddof=1": r.var(ddof=1), "var ddof=0": r.var(ddof=0)})
    cmp("S annual_volatility", P("annual_volatility"), {"std ddof=1 * sqrt(A)": r.std(ddof=1) * math.sqrt(A), "ddof=0": r.std(ddof=0) * math.sqrt(A)})
    rfp = {"rf/A": rf / A, "(1+rf)^(1/A)-1": (1 + rf) ** (1 / A) - 1}; mp = {"mar/A": mar / A, "(1+mar)^(1/A)-1": (1 + mar) ** (1 / A) - 1}
    dd = {k: math.sqrt(np.mean(np.minimum(r - m, 0) ** 2)) for k, m in mp.items()}
    cmp("S downside_deviation", P("downside_deviation"), {f"sqrt(mean(min(r-m,0)^2)) all periods, m={k}": v for k, v in dd.items()})
    cmp("S annual_downside_volatility", P("annual_downside_volatility"), {f"dd*sqrt(A), m={k}": v * math.sqrt(A) for k, v in dd.items()})
    sh = {k: (r - p).mean() / (r - p).std(ddof=1) * math.sqrt(A) for k, p in rfp.items()}
    cmp("S sharpe", P("sharpe"), {f"mean(e)/std(e,ddof=1)*sqrt(A), rf={k}": v for k, v in sh.items()})
    cmp("S sortino", P("sortino"), {f"mean(r-m)*A/(dd*sqrt(A)), m={k}": (r - m).mean() * A / (dd[k] * math.sqrt(A)) for k, m in mp.items()})
    V = np.concatenate([[V0], eq]); D, D1, eps = dd_stats(V); mdd = -D.min()
    cmp("S max_drawdown", P("max_drawdown"), {"-min(V_t/P_t-1), P includes V_0": mdd, "without V_0": -(eq / np.maximum.accumulate(eq) - 1).min()})
    cmp("S current_drawdown", P("current_drawdown"), {"-D_N": -D[-1]})
    cmp("S calmar", P("calmar"), {"cagr/mdd": P("cagr") / mdd if mdd else float("nan")})
    ul = {"sqrt(mean(D_1..N^2))": math.sqrt(np.mean(D1 ** 2)), "incl. D_0": math.sqrt(np.mean(D ** 2))}
    ulab = cmp("S ulcer_index", P("ulcer_index"), ul); u = ul.get(ulab, ul["sqrt(mean(D_1..N^2))"])
    cmp("S martin", P("martin"), {"mean(r-m)*A/ulcer": (r - mp["mar/A"]).mean() * A / u, "cagr/ulcer": P("cagr") / u, "annual_arithmetic_mean/ulcer": r.mean() * A / u})
    m0 = mp["mar/A"]
    cmp("S omega", P("omega"), {"sum(max(r-m,0))/sum(max(m-r,0))": np.maximum(r - m0, 0).sum() / np.maximum(m0 - r, 0).sum()})
    cmp("S gain_to_pain", P("gain_to_pain"), {"sum(r)/sum(|r<0|)": r.sum() / np.abs(r[r < 0]).sum()})
    cmp("S hit_rate", P("hit_rate"), {"share r>0": float(np.mean(r > 0)), "share r>=0": float(np.mean(r >= 0))})
    cmp("S best_period", P("best_period"), {"max": r.max()}); cmp("S worst_period", P("worst_period"), {"min": r.min()})
    cmp("S time_under_water", P("time_under_water"), {"share D_t<0 (t=1..N)": float(np.mean(D1 < 0)), "incl. D_0": float(np.mean(D < 0))})
    cmp("S average_drawdown", P("average_drawdown"), {"mean(-D_t) all sessions": float(np.mean(-D1)), "mean(-D_t | D_t<0)": float(np.mean(-D1[D1 < 0])) if (D1 < 0).any() else 0.0, "mean of episode troughs": float(np.mean([-D1[t] for _, _, t, _ in eps])) if eps else 0.0})
    cmp("S drawdown_episodes", P("drawdown_episodes"), {"count of D_t<0 runs": len(eps)})
    durs = [(j - i) + (0 if rec else 0) for i, j, t, rec in eps]; durs2 = [(j - i + 1) for i, j, t, rec in eps]
    cmp("S max_drawdown_duration", P("max_drawdown_duration"), {"longest run of D_t<0 (sessions under water)": max(durs) if durs else 0, "run+1 (peak to recovery)": max(durs2) if durs2 else 0})
    recs = [(j - t) for i, j, t, rec in eps if rec]; recs_all = [(j - t) for i, j, t, rec in eps]
    cmp("S max_recovery_duration", P("max_recovery_duration"), {"trough->recovery, recovered episodes": max(recs) if recs else 0, "trough->end incl. censored": max(recs_all) if recs_all else 0})
    q = {m: float(np.quantile(r, 0.05, method=m)) for m in ("linear", "lower", "higher", "nearest", "midpoint", "hazen", "weibull", "median_unbiased", "normal_unbiased")}
    vlab = cmp("S var_loss_95", P("var_loss_95"), {f"-quantile(r,0.05,{k})": -v for k, v in q.items()})
    cmp("S expected_shortfall_95", P("expected_shortfall_95"), {f"-mean(r<=q_{k})": -float(np.mean(r[r <= v])) for k, v in q.items()} | {"-mean of worst ceil(5%n)": -float(np.mean(np.sort(r)[: math.ceil(0.05 * n)])), "-mean of worst floor(5%n)": -float(np.mean(np.sort(r)[: max(1, math.floor(0.05 * n))]))})
    mm = r - r.mean(); s2 = np.mean(mm ** 2)
    cmp("S skewness", P("skewness"), {"population m3/m2^1.5": float(np.mean(mm ** 3) / s2 ** 1.5), "sample-adjusted (pandas)": float(pd.Series(r).skew())})
    cmp("S excess_kurtosis", P("excess_kurtosis"), {"population m4/m2^2-3": float(np.mean(mm ** 4) / s2 ** 2 - 3), "sample-adjusted (pandas)": float(pd.Series(r).kurt())})
    if "benchmark" in M and "benchmark_return" in d:
        b = d.benchmark_return.to_numpy(float); act = r - b; B = lambda k: val(M, "benchmark", k)
        cmp("S benchmark_total_return", B("benchmark_total_return"), {"prod(1+b)-1 over all n sessions": float(np.prod(1 + b) - 1), "excluding first session": float(np.prod(1 + b[1:]) - 1)})
        cmp("S tracking_error", B("tracking_error"), {"std(r-b,ddof=1)*sqrt(A)": act.std(ddof=1) * math.sqrt(A)})
        cmp("S information_ratio", B("information_ratio"), {"mean(r-b)/std(r-b,ddof=1)*sqrt(A)": act.mean() / act.std(ddof=1) * math.sqrt(A)})
        cmp("S correlation", B("correlation"), {"corr(r,b)": float(np.corrcoef(r, b)[0, 1])})
        beta = float(np.cov(r, b, ddof=1)[0, 1] / np.var(b, ddof=1)); cmp("S beta", B("beta"), {"cov/var": beta})
        cmp("S alpha_annual", B("alpha_annual"), {"(mean r - beta mean b)*A": (r.mean() - beta * b.mean()) * A, "CAPM with rf": ((r - rfp['rf/A']).mean() - beta * (b - rfp['rf/A']).mean()) * A})
        out("INFO", "S first session", f"return {r[0]!r}, positions {int(d.n_long.iloc[0] + d.n_short.iloc[0])}, benchmark_return {b[0]!r} (benchmark compounds from the first session while the portfolio is flat until the first fill)")
    if "gross_of_costs" in M:
        Vg = V0 * np.cumprod(1 + g); G = lambda k: val(M, "gross_of_costs", k)
        cmp("S gross total_return", G("total_return"), {"prod(1+g)-1": Vg[-1] / V0 - 1}); cmp("S gross cagr", G("cagr"), {f"Y={ylab}": (Vg[-1] / V0) ** (1 / Y) - 1})
        cmp("S gross annual_volatility", G("annual_volatility"), {"std ddof=1 sqrt(A)": g.std(ddof=1) * math.sqrt(A)})
        cmp("S gross sharpe", G("sharpe"), {"mean(e)/std(e)*sqrt(A)": (g - rfp['rf/A']).mean() / (g - rfp['rf/A']).std(ddof=1) * math.sqrt(A)})
        Vg0 = np.concatenate([[V0], Vg]); cmp("S gross max_drawdown", G("max_drawdown"), {"-min(D), P incl V_0": -(Vg0 / np.maximum.accumulate(Vg0) - 1).min()})
    H = S["hac_mean_return"]; h = hac(r)
    cmp("S hac lags", H.get("lags"), {"floor(4 (n/100)^(2/9))": h["lags"]}); cmp("S hac se", H.get("se"), {"Newey-West Bartlett": h["se"]}); cmp("S hac t_stat", H.get("t_stat"), {"mean/se": h["t"]})
    cmp("S hac p_two_sided", H.get("p_two_sided"), {"2(1-Phi(|t|))": 2 * (1 - ND.cdf(abs(h["t"])))})
    e = r - rfp["rf/A"]; p0 = psr(e, 0.0); PS = S["probabilistic_sharpe_vs_zero"]
    cmp("S psr", PS.get("psr"), {"Phi((SR-0)sqrt(n-1)/sqrt(1-g3 SR+(g4-1)/4 SR^2))": p0["p"]}); cmp("S psr skewness", PS.get("skewness"), {"population": p0["skew"]}); cmp("S psr kurtosis (raw)", PS.get("kurtosis"), {"population m4/m2^2": p0["kurt"]})
    DS = S["deflated_sharpe"]; nt = DS.get("n_trials"); var = DS.get("trial_sr_variance")
    cmp("S dsr trial_sr_variance", var, {"1/(n-1)": 1 / (n - 1)})
    sr0 = 0.0 if nt < 2 else math.sqrt(var) * ((1 - EG) * ND.inv_cdf(1 - 1 / nt) + EG * ND.inv_cdf(1 - 1 / (nt * math.e)))
    cmp("S dsr expected max SR", DS.get("benchmark_sharpe_per_period"), {"sqrt(V)((1-g)Z(1-1/N)+g Z(1-1/(Ne)))": sr0}); cmp("S dsr", DS.get("dsr"), {"PSR(SR0)": psr(e, sr0)["p"]})
    AC = S.get("return_autocorrelation", {})
    for k in range(1, 6):
        if f"lag_{k}" in AC: cmp(f"S autocorr lag_{k}", AC[f"lag_{k}"], {"pearson(r_t, r_t-k)": float(np.corrcoef(r[k:], r[:-k])[0, 1])})
    # mining diagnostics
    mic = root / "mining/diagnostics/tables/daily_ic.csv"
    if mic.exists():
        ic = pd.read_csv(mic); MM = json.loads((root / "mining/diagnostics/metrics.json").read_text()); x = ic.ic.dropna().to_numpy(float)
        cmp("S mining mean_ic", MM.get("mean_ic"), {"mean": x.mean()}); cmp("S mining std_ic", MM.get("std_ic"), {"ddof=1": x.std(ddof=1), "ddof=0": x.std(ddof=0)})
        cmp("S mining icir", MM.get("icir"), {"mean/std ddof=1": x.mean() / x.std(ddof=1), "ddof=0": x.mean() / x.std(ddof=0)}); cmp("S mining positive_share", MM.get("positive_share"), {"share ic>0": float(np.mean(x > 0))})
        cmp("S mining valid_dates", MM.get("valid_dates"), {"non-null ic": len(x)}); cmp("S mining total_dates", MM.get("total_dates"), {"rows": len(ic)})
        ht = MM.get("hac_test", {}); hh = hac(x, ht.get("lags")); cmp("S mining hac t_stat", ht.get("t_stat"), {"Newey-West": hh["t"]}); cmp("S mining hac lags", ht.get("lags"), {"floor(4 (n/100)^(2/9))": hac(x)["lags"]})
    # reported outputs
    sec = None; mism = []; rows = 0; groups = {"Performance": "performance", "Gross Of Costs": "gross_of_costs", "Trading": "trading", "Trades": "trades", "Benchmark": "benchmark", "External Benchmark": "external_benchmark"}
    for line in (E / "report.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "): sec = line[3:].strip(); continue
        if sec in groups and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 2 or cells[0] in ("metric", "field") or set(cells[0]) <= {"-"}: continue
            k, s = cells; v = val(M, groups[sec], k); rows += 1
            if v is None or not isinstance(v, (int, float)) or isinstance(v, bool): continue
            try:
                if s.endswith("%"): num = float(s[:-1].replace(",", "")); dec = len(s[:-1].split(".")[1]) if "." in s else 0; ok = abs(num - v * 100) <= 0.5 * 10 ** -dec + 1e-9
                else: num = float(s.replace(",", "")); dec = len(s.split(".")[1]) if "." in s else 0; ok = abs(num - v) <= 0.5 * 10 ** -dec + 1e-9
            except ValueError: ok = True
            if not ok: mism.append((sec, k, s, v))
    out("PASS" if not mism else "FAIL", "R1 report.md metric tables vs metrics.json", f"{rows} rows compared; mismatches {mism}")
    chk = {c["name"]: c for c in VD["portfolio"]["checks"]}; stress = {row.scenario: row for row in sc.itertuples()}
    exp = {"sessions": P("periods"), "net_sharpe_validity": P("sharpe"), "net_sharpe_ci": S["bootstrap"].get("sharpe_ci"), "deflated_sharpe": DS.get("dsr"), "solvency": bool(eq.min() > 0)}
    for name, c in chk.items():
        if name in exp: cmp(f"R2 verdict check {name}", json.dumps(c["value"]), {"source value": json.dumps(exp[name])}) if isinstance(c["value"], list) else cmp(f"R2 verdict check {name}", c["value"], {"source": exp[name]})
        elif name.startswith("stress:"):
            sname = name.split(":", 1)[1]; cmp(f"R2 verdict check {name}", c["value"], {"scenarios.csv sharpe": getattr(stress.get(sname), "sharpe", None)})
        else: out("INFO", f"R2 verdict check {name}", f"value {c['value']} threshold {c['threshold']} (no independent source mapped)")
    base = stress.get("base")
    if base is not None:
        for k, src in (("cagr", P("cagr")), ("sharpe", P("sharpe")), ("max_drawdown", P("max_drawdown")), ("total_costs", T("total_costs")), ("turnover_one_way_annual", T("turnover_one_way_annual"))): cmp(f"R3 scenarios base.{k}", getattr(base, k), {"main run": src})
    sm = root / "signals/manifest.json"
    if sm.exists():
        fe = json.loads(sm.read_text()).get("metadata", {}).get("factor_evidence"); vf = VD.get("factor", {})
        if fe is None: out("PASS" if vf.get("status") == "not_confirmed" and "no factor confirmation evidence" in str(vf.get("reason")) else "FAIL", "R4 verdict.factor with signals that carry no evidence", f"verdict.factor {vf}")
        else: out("PASS" if fe == vf else "FAIL", "R4 verdict.factor == signals manifest factor_evidence", f"equal {fe == vf}")
    figs = sorted((E / "figures").glob("*")); out("PASS" if figs and all(p.stat().st_size > 0 for p in figs) else "FAIL", "R5 figures present and non-empty", str([p.name for p in figs]))
    # trades/episodes vs metrics
    Tr = lambda k: val(M, "trades", k); est = ep.status.value_counts().to_dict(); out("INFO", "A10 episode statuses", str(est))
    cl = ep[ep.status == "closed"]; pnl = cl.pnl.to_numpy(float); w = pnl[pnl > 0]; lo = pnl[pnl < 0]
    for k, v in {"closed_trades": len(cl), "open_trades": int((ep.status != "closed").sum()), "wins": len(w), "losses": len(lo), "flats": int((pnl == 0).sum()), "win_rate": len(w) / len(cl) if len(cl) else None, "non_flat_win_rate": len(w) / (len(w) + len(lo)) if len(w) + len(lo) else None, "average_trade_pnl": pnl.mean() if len(pnl) else None, "median_trade_pnl": float(np.median(pnl)) if len(pnl) else None, "average_win": w.mean() if len(w) else None, "average_loss": lo.mean() if len(lo) else None, "payoff_ratio": (w.mean() / abs(lo.mean())) if len(w) and len(lo) else None, "profit_factor": (w.sum() / abs(lo.sum())) if len(lo) else None, "expectancy": (len(w) / len(cl) * w.mean() + len(lo) / len(cl) * lo.mean()) if len(cl) and len(w) and len(lo) else None, "total_closed_trade_pnl": pnl.sum(), "best_trade": pnl.max() if len(pnl) else None, "worst_trade": pnl.min() if len(pnl) else None, "average_holding_sessions": float(cl.holding_sessions.mean()) if len(cl) else None, "median_holding_sessions": float(cl.holding_sessions.median()) if len(cl) else None, "long_trades": int((cl.side == "long").sum()), "short_trades": int((cl.side == "short").sum())}.items():
        if k in M.get("trades", {}): cmp(f"A10 trades.{k}", Tr(k), {"from episodes.csv": v}, rel=1e-9, ab=1e-6)
    # timing
    mk = root / "data/market/data.parquet"
    if mk.exists():
        import pyarrow.parquet as pq
        mt = pq.read_table(mk, columns=["date", "instrument"]).to_pandas(); sessions = sorted({str(x) for x in mt.date}); src = "market bundle"
    else: sessions = list(d.date); src = "daily.csv"
    pos = {s: i for i, s in enumerate(sessions)}; bad = []; look = int((f.date <= f.decision_date).sum())
    for row in f.itertuples():
        i = pos.get(row.decision_date); j = pos.get(row.date)
        if i is None or j is None or j != i + 1 + ex["delay"]: bad.append((row.date, row.decision_date, row.instrument))
    out("PASS" if not bad and not look else "FAIL", "T1 fill date = next session after decision_date (+delay)", f"sessions from {src}; {len(f)} fills, {len(bad)} off-schedule, {look} on/before decision date; examples {bad[:3]}")
    ew = VD["portfolio"].get("evaluation_window", {}); out("PASS" if ew.get("start") == d.date.iloc[0] and ew.get("end") == d.date.iloc[-1] else "FAIL", "T2 verdict evaluation_window == daily.csv span", f"{ew} vs {d.date.iloc[0]}..{d.date.iloc[-1]}")
    cw = VD.get("factor", {}).get("confirmation_window"); out("INFO", "T3 factor confirmation_window vs evaluation window", f"{cw} vs {ew}")
    sp = root / "signals/data.parquet"
    if sp.exists():
        import pyarrow.parquet as pq
        sg = pq.read_table(sp, columns=["decision_date"]).to_pandas(); sd = sorted({str(x) for x in sg.decision_date})
        out("PASS" if all(s in pos for s in sd) else "FAIL", "T4 signal decision dates are market sessions", f"{len(sd)} dates {sd[0]}..{sd[-1]}; market {sessions[0]}..{sessions[-1]}; first signal is session #{pos.get(sd[0])}")
        if mk.exists():
            mm_ = json.loads((root / "data/market/manifest.json").read_text()).get("metadata", {}); smd = json.loads(sm.read_text()).get("metadata", {})
            out("PASS" if mm_.get("timezone") else "FAIL", "T5 market manifest declares timezone/calendar", f"timezone {mm_.get('timezone')} calendar {mm_.get('calendar')}")
            out("INFO", "T5 signals manifest time semantics", f"available_at {smd.get('available_at')}, timezone {smd.get('timezone', 'absent')}, calendar {smd.get('calendar', 'absent')}")
    out("INFO", "T6 data span", f"market {sessions[0]}..{sessions[-1]}; evaluation {d.date.iloc[0]}..{d.date.iloc[-1]}")
    print(f"TOTAL FAIL={fails}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
