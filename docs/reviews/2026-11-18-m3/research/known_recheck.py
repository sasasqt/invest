import numpy as np
import pandas as pd

from invest_evaluation.stats import bootstrap_ci, newey_west_mean
from invest_mining.diagnostics import benjamini_hochberg, holm_adjust
from invest_mining.expressions import check_scale_free, parse

x = np.full(300, 0.0001) + np.r_[1e-19, np.zeros(299)]
x = np.ones(300) * 0.1 / 252
print(
    "BH-2026-11-18-2 constant series HAC:",
    {k: newey_west_mean(x).get(k) for k in ("status", "t_stat")},
    "bootstrap:",
    bootstrap_ci(pd.Series(x), 252)["status"],
)
print(
    "BH-2026-11-18-3 BH with NaN:",
    [round(v, 3) for v in benjamini_hochberg([0.01, 0.04, 0.03, 0.04, float("nan"), 0.20])],
)
print("BH-2026-10-14-4 Holm with NaN:", holm_adjust([0.01, float("nan"), 0.02, 0.03]))
for e in ("cs_rank(-close)", "close / delay(close, 5) - 1", "cs_rank(volume)", "fund_eps / close"):
    try:
        check_scale_free(parse(e))
        print("scale check passes:", e)
    except Exception as exc:
        print("scale check refuses:", e, "->", type(exc).__name__)
