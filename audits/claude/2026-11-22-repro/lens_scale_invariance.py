"""Lens (exploitation, new decision code of #51): is check_scale_free sound?

Independent oracle (no use of the code's scale algebra): rescale ONE instrument's whole
adjusted history the way a later split or dividend does (open/high/low/close x c, volume / c,
close_as_traded unchanged; DATA_CONTRACT: volume adjusted inversely) and evaluate the formula
on both panels. A formula the check accepts must give the same values on every date for every
instrument (expressions.py check_scale_free docstring: "Raise ScaleError unless a later split
or dividend leaves the value unchanged"). c = 2 makes the rescaling exact in binary floating
point, so a pow-scaled computation changes by at most rounding of log/shift terms.

Usage: python -I lens_scale_invariance.py <n_formulas> <seed> <out.json>
Exit 1 when an accepted formula changes (soundness violation), 0 otherwise; refusals of
formulas that stay unchanged are counted as over-refusals (usability, not a defect).
"""
from __future__ import annotations
import json, sys
import numpy as np
import pandas as pd
from invest_mining.expressions import (FEATURES, TS_OPS, WINDOWS, Call, Const, Feature, ScaleError,
                                       build_panel, check_scale_free, evaluate, parse)

n, seed, outp = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
rng = np.random.default_rng(seed)
feats = list(FEATURES) + ["close_as_traded"]

def grow(d: int):
    if d <= 1 or rng.random() < 0.25:
        if rng.random() < 0.05:
            return Const(float(rng.choice([0.5, 2.0, 3.0])))
        return Feature(str(rng.choice(feats)))
    kind = rng.choice(["unary", "binary", "ts", "ts", "ts2", "cs"])
    if kind == "unary":
        return Call(str(rng.choice(["neg", "abs", "log", "sign"])), (grow(d - 1),))
    if kind == "binary":
        b = Const(float(rng.choice([0.5, 2.0]))) if rng.random() < 0.15 else grow(d - 1)
        return Call(str(rng.choice(["add", "sub", "mul", "div"])), (grow(d - 1), b))
    if kind == "ts":
        return Call(str(rng.choice(TS_OPS)), (grow(d - 1),), int(rng.choice(WINDOWS[:4])))
    if kind == "ts2":
        return Call("ts_corr", (grow(d - 1), grow(d - 1)), int(rng.choice(WINDOWS[2:4])))
    return Call(str(rng.choice(["cs_rank", "cs_zscore", "cs_demean"])), (grow(d - 1),))

# deterministic market: 6 instruments, 90 sessions, random walks, no flat windows
drng = np.random.default_rng(12345)
dates = pd.bdate_range("2024-01-02", periods=90)
rows = []
for i in range(6):
    px = 40 * np.exp(np.cumsum(drng.normal(0, 0.02, len(dates)))) + i
    op = px * np.exp(drng.normal(0, 0.005, len(dates)))
    hi = np.maximum(px, op) * (1 + np.abs(drng.normal(0, 0.004, len(dates))))
    lo = np.minimum(px, op) * (1 - np.abs(drng.normal(0, 0.004, len(dates))))
    vol = drng.uniform(1e5, 5e5, len(dates))
    for k, d in enumerate(dates):
        rows.append({"date": d, "instrument": f"I{i}", "open": op[k], "high": hi[k], "low": lo[k],
                     "close": px[k], "volume": vol[k], "close_as_traded": px[k] * (1.5 if i % 2 else 0.8)})
bars = pd.DataFrame(rows)

def rescaled(c: float, inst: str) -> pd.DataFrame:
    b = bars.copy(); m = b["instrument"] == inst
    for f in ("open", "high", "low", "close"):
        b.loc[m, f] = b.loc[m, f] * c
    b.loc[m, "volume"] = b.loc[m, "volume"] / c
    return b

P0 = build_panel(bars)
alts = [(2.0, "I0"), (0.5, "I3"), (3.0, "I4")]
Ps = [(c, inst, build_panel(rescaled(c, inst))) for c, inst in alts]

def same(a: pd.DataFrame, b: pd.DataFrame, exact: bool) -> tuple[bool, float]:
    x, y = a.to_numpy(float), b.to_numpy(float)
    nan_x, nan_y = np.isnan(x), np.isnan(y)
    if (nan_x != nan_y).any():
        return False, float("inf")
    ok = ~nan_x
    if not ok.any():
        return True, 0.0
    d = np.abs(x[ok] - y[ok]); scale = np.maximum(1.0, np.maximum(np.abs(x[ok]), np.abs(y[ok])))
    worst = float((d / scale).max())
    return worst <= (1e-9 if exact else 1e-6), worst

res = {"accepted_changed": [], "accepted_same": 0, "refused_same_all": [], "refused_changed": 0,
       "eval_errors": 0, "all_nan": 0, "n": 0, "seed": seed}
seen = set()
while res["n"] < n:
    try:
        node = parse(str(grow(4)))
    except Exception:
        continue  # the grammar refuses it (e.g. an operator over constants only)
    text = str(node)
    if text in seen:
        continue
    seen.add(text); res["n"] += 1
    try:
        check_scale_free(node); accepted = True; msg = ""
    except ScaleError as e:
        accepted = False; msg = str(e)[:160]
    except Exception as e:
        res["eval_errors"] += 1; continue
    try:
        v0 = evaluate(node, P0)
    except Exception:
        res["eval_errors"] += 1; continue
    if v0.isna().all().all():
        res["all_nan"] += 1; continue
    verdicts = []
    for c, inst, P in Ps:
        v = evaluate(node, P)
        verdicts.append((c, inst) + same(v0, v, exact=(c in (2.0, 0.5))))
    changed = [vv for vv in verdicts if not vv[2]]
    if accepted and changed:
        res["accepted_changed"].append({"expr": text, "changed": [[c, i, w] for c, i, ok, w in changed]})
    elif accepted:
        res["accepted_same"] += 1
    elif not changed:
        res["refused_same_all"].append({"expr": text, "msg": msg})
    else:
        res["refused_changed"] += 1
open(outp, "w", encoding="utf-8").write(json.dumps(res, indent=1))
print({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()})
for item in res["accepted_changed"][:15]:
    print("ACCEPTED BUT CHANGED:", item)
for item in res["refused_same_all"][:8]:
    print("refused although unchanged:", item["expr"], "|", item["msg"][:100])
sys.exit(1 if res["accepted_changed"] else 0)
